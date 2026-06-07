"""Extended data-gathering for the React control-centre dashboard.

Like :mod:`eidetic_os.dashboard.data`, every function here is pure, Flask-free,
and individually testable: it reads live state from the existing Eidetic OS
modules and returns plain JSON-ready dictionaries. Nothing imports Flask.

These functions back the JSON API the single-page React dashboard consumes
(``/api/overview``, ``/api/memory``, ``/api/security`` …). They deliberately
*never raise* for the ordinary "not set up yet" cases — a missing vault, an empty
fact store, an unsigned audit trail — returning an ``available``/``reason`` shape
the UI renders as a calm empty state rather than a 500.
"""

from __future__ import annotations

import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eidetic_os import __version__, audit
from eidetic_os.dashboard import data

# Process start time, so the Overview can show dashboard uptime without a DB.
_BOOT_MONOTONIC = time.monotonic()


# ── shared helpers ────────────────────────────────────────────────────────────
def _open_fact_store() -> Any | None:
    """Open the conventional fact store read-only/offline, or ``None``.

    Returns ``None`` (rather than creating an empty DB) when the facts database
    does not exist yet, so callers can show a "no memory captured" empty state.
    """
    from eidetic_os import facts

    db_path = facts.facts_db_path()
    if not db_path.exists():
        return None
    try:
        return facts.FactStore(db_path)  # offline: no embedder needed for reads
    except Exception:  # pragma: no cover - corrupt DB edge case
        return None


def _fact_to_dict(fact: Any) -> dict[str, Any]:
    return {
        "id": fact.id,
        "fact": fact.fact,
        "source": fact.source,
        "category": fact.category,
        "tier": getattr(fact, "tier", "recall"),
        "confidence": round(float(fact.confidence), 3),
        "relevance": round(float(getattr(fact, "relevance_score", 1.0)), 4),
        "access_count": fact.access_count,
        "created_at": str(fact.created_at)[:19].replace("T", " "),
        "last_accessed": str(fact.last_accessed)[:19].replace("T", " "),
    }


def _uptime_human() -> str:
    seconds = max(0.0, time.monotonic() - _BOOT_MONOTONIC)
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


# ── 1. Overview ───────────────────────────────────────────────────────────────
def overview() -> dict[str, Any]:
    """The system-health-at-a-glance payload for the Overview tab."""
    vectors = data.vector_stats()
    graph = _safe(lambda: data.graph_data(max_nodes=4000), default={})

    # Health summary (reuse the doctor) — guarded, never fatal to the payload.
    health = _safe(data.health_report, default={"summary": {}, "overall": "warn"})
    summary = health.get("summary", {})

    # Fact / tier aggregates.
    facts_total = 0
    tiers = {"core": 0, "recall": 0, "archival": 0}
    categories: dict[str, int] = {}
    store = _open_fact_store()
    if store is not None:
        try:
            facts_total = store.count(active_only=True)
            for fact in store.active_facts():
                tiers[getattr(fact, "tier", "recall")] = (
                    tiers.get(getattr(fact, "tier", "recall"), 0) + 1
                )
                categories[fact.category] = categories.get(fact.category, 0) + 1
        finally:
            store.close()

    # LLM backend (no network probe here — keep Overview fast; just report config).
    backend = _backend_summary()

    # Audit crypto chain integrity (cheap: reads the trail once).
    chain = _chain_summary()

    recent = audit.read_audit(limit=8)
    recent.reverse()
    recent_rows = [
        {
            "action": str(e.get("action", "")),
            "status": str(e.get("status", "")),
            "trigger": str(e.get("trigger", "")),
            "context": str(e.get("context", ""))[:80],
            "timestamp": str(e.get("timestamp", ""))[:19].replace("T", " "),
        }
        for e in recent
    ]

    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.system(),
        "uptime": _uptime_human(),
        "vault_path": _vault_str(),
        "health": {
            "overall": health.get("overall", "warn"),
            "ok": summary.get("ok", 0),
            "warn": summary.get("warn", 0),
            "fail": summary.get("fail", 0),
            "total": summary.get("total", 0),
        },
        "vectors": {
            "available": vectors.get("available", False),
            "chunks": vectors.get("chunk_count", 0),
            "files": vectors.get("file_count", 0),
            "backend": vectors.get("backend", "—"),
            "db_size": vectors.get("db_size", "—"),
            "last_embed": vectors.get("last_embed"),
        },
        "graph": graph.get("stats", {}) if isinstance(graph, dict) else {},
        "memory": {
            "total": facts_total,
            "tiers": tiers,
            "categories": categories,
        },
        "backend": backend,
        "chain": chain,
        "recent_audit": recent_rows,
    }


# ── 2. Memory ─────────────────────────────────────────────────────────────────
def memory(query: str = "", category: str = "", limit: int = 60) -> dict[str, Any]:
    """Fact-store browser + tier occupancy + decay/relevance distribution."""
    store = _open_fact_store()
    if store is None:
        return {
            "available": False,
            "reason": "no facts captured yet — run `eidetic remember` or let "
            "sleeptime consolidation populate the store.",
            "facts": [],
            "tiers": {"counts": {}, "sizes": {}, "limits": {}, "total": 0},
            "categories": [],
            "relevance_buckets": [],
            "hot": [],
            "stale": [],
        }

    try:
        from eidetic_os.memory_scoring import MemoryScorer
        from eidetic_os.memory_tiers import TieredMemory

        all_active = store.active_facts()

        # Filter for the browser table.
        q = query.strip().lower()
        rows = [
            f
            for f in all_active
            if (not category or f.category == category)
            and (not q or q in f.fact.lower() or q in f.source.lower())
        ]
        rows.sort(key=lambda f: float(getattr(f, "relevance_score", 1.0)), reverse=True)
        facts_out = [_fact_to_dict(f) for f in rows[:limit]]

        # Category breakdown over the *unfiltered* active set.
        cat_counts: dict[str, int] = {}
        for f in all_active:
            cat_counts[f.category] = cat_counts.get(f.category, 0) + 1
        categories = sorted(
            ({"name": k, "count": v} for k, v in cat_counts.items()),
            key=lambda d: d["count"],
            reverse=True,
        )

        # Tier occupancy.
        tier_stats = TieredMemory(store=store).as_dict()

        # Relevance distribution (10 buckets, 0.0–1.0+).
        buckets = [0] * 10
        for f in all_active:
            score = float(getattr(f, "relevance_score", 1.0))
            idx = min(9, max(0, int(score * 10)))
            buckets[idx] += 1
        relevance_buckets = [
            {"range": f"{i/10:.1f}", "count": n} for i, n in enumerate(buckets)
        ]

        scorer = MemoryScorer(store)
        hot = [_fact_to_dict(f) for f in scorer.get_hot(limit=8)]
        stale = [_fact_to_dict(f) for f in scorer.get_stale(threshold=0.35, limit=8)]

        return {
            "available": True,
            "total": len(all_active),
            "shown": len(facts_out),
            "facts": facts_out,
            "tiers": tier_stats,
            "categories": categories,
            "relevance_buckets": relevance_buckets,
            "hot": hot,
            "stale": stale,
            "consolidation": _consolidation_log(),
        }
    finally:
        store.close()


def _consolidation_log(limit: int = 12) -> list[dict[str, Any]]:
    """Recent sleeptime-consolidation runs, newest first."""
    entries = audit.read_audit(action="consolidate", limit=limit)
    entries.reverse()
    return [
        {
            "timestamp": str(e.get("timestamp", ""))[:19].replace("T", " "),
            "status": str(e.get("status", "")),
            "changes": list(e.get("changes", []) or []),
            "context": str(e.get("context", "")),
        }
        for e in entries
    ]


# ── 3. Security ───────────────────────────────────────────────────────────────
def security() -> dict[str, Any]:
    """Audit-trail signature verification, hash-chain integrity, recent gates."""
    chain = _chain_full()

    # Recent verification-gate (GROUND pipeline) runs from the audit trail.
    verify_entries = audit.read_audit(action="verify", limit=15)
    verify_entries.reverse()
    gate_runs = [
        {
            "timestamp": str(e.get("timestamp", ""))[:19].replace("T", " "),
            "status": str(e.get("status", "")),
            "context": str(e.get("context", "")),
            "tiers": list(e.get("changes", []) or []),
            "error": e.get("error"),
            "duration": e.get("duration_seconds"),
        }
        for e in verify_entries
    ]

    # The five GROUND tiers (static description for the pipeline diagram).
    tiers = [
        {"key": "syntax", "label": "Syntax", "desc": "AST parse — every file compiles"},
        {"key": "imports", "label": "Imports", "desc": "No missing local modules"},
        {"key": "tests", "label": "Tests", "desc": "pytest suite passes"},
        {"key": "runtime", "label": "Runtime", "desc": "Entrypoint imports clean in sandbox"},
        {"key": "diff", "label": "Diff", "desc": "Changes stay within declared scope"},
    ]

    return {
        "chain": chain,
        "gate_runs": gate_runs,
        "tiers": tiers,
        "signer_available": chain.get("signer_available", False),
    }


def _audit_trail_path() -> Path:
    return audit.audit_path()


def _chain_summary() -> dict[str, Any]:
    """Cheap chain-integrity snapshot for the Overview."""
    full = _chain_full()
    return {
        "intact": full.get("chain_intact", False),
        "signer_available": full.get("signer_available", False),
        "total": full.get("total_entries", 0),
        "verified": full.get("verified", 0),
    }


def _chain_full() -> dict[str, Any]:
    """Verify the whole audit trail's signatures and hash chain."""
    try:
        from eidetic_os import audit_crypto

        signer = audit_crypto.get_default_signer()
        path = _audit_trail_path()
        if signer is None or not signer.available:
            # Count entries even when signing isn't configured.
            total = len(audit.read_audit(limit=-1))
            return {
                "signer_available": False,
                "total_entries": total,
                "verified": 0,
                "unsigned": total,
                "tampered": 0,
                "first_tampered_line": None,
                "chain_intact": False,
                "public_key": None,
            }
        result = signer.verify_trail(path)
        public_key = _safe(lambda: signer._public_to_b64(signer._public), default=None)  # type: ignore[attr-defined]
        return {
            "signer_available": True,
            "total_entries": result.total_entries,
            "verified": result.verified,
            "unsigned": result.unsigned,
            "tampered": result.tampered,
            "first_tampered_line": result.first_tampered_line,
            "chain_intact": result.chain_intact,
            "public_key": public_key,
        }
    except Exception as exc:  # pragma: no cover - crypto backend missing
        return {
            "signer_available": False,
            "total_entries": 0,
            "verified": 0,
            "unsigned": 0,
            "tampered": 0,
            "first_tampered_line": None,
            "chain_intact": False,
            "public_key": None,
            "error": str(exc),
        }


# ── 4. Pipelines ──────────────────────────────────────────────────────────────
def pipelines() -> dict[str, Any]:
    """Scheduled automations with cadence, install state, and last/next run."""
    tasks = data.scheduled_tasks()
    enriched = []
    for t in tasks:
        last = t.get("last_run")
        state = "idle"
        if last is not None:
            state = {"ok": "success", "fail": "failed", "warn": "warning"}.get(
                last.get("state", ""), "idle"
            )
        if not t.get("installed"):
            state = "disabled"
        enriched.append({**t, "state": state})

    running = sum(1 for t in enriched if t["state"] == "success")
    failed = sum(1 for t in enriched if t["state"] == "failed")
    installed = sum(1 for t in enriched if t.get("installed"))
    return {
        "tasks": enriched,
        "summary": {
            "total": len(enriched),
            "installed": installed,
            "ok": running,
            "failed": failed,
        },
    }


# ── 5. Settings ───────────────────────────────────────────────────────────────
def settings() -> dict[str, Any]:
    """Configuration snapshot: LLM/vector backends, paths, memory params."""
    from eidetic_os import config, vector_backend

    vector_active = _safe(vector_backend.active_backend_name, default="sqlite")
    forced_llm = os.environ.get("EIDETIC_LLM_BACKEND") or None
    params = _safe(config.memory_params, default={})

    llm_backends = [
        {"name": "lmstudio", "label": "LM Studio", "default": "http://localhost:5555"},
        {"name": "ollama", "label": "Ollama", "default": "http://localhost:11434"},
        {"name": "llamacpp", "label": "llama.cpp", "default": "http://localhost:8080"},
        {"name": "openai-compatible", "label": "OpenAI-compatible", "default": "—"},
    ]
    vector_backends = [
        {"name": "sqlite", "label": "SQLite (sqlite-vec)", "builtin": True},
        {"name": "lancedb", "label": "LanceDB", "builtin": False},
        {"name": "chromadb", "label": "ChromaDB", "builtin": False},
        {"name": "valkey", "label": "Valkey", "builtin": False},
    ]

    return {
        "llm_backends": llm_backends,
        "llm_forced": forced_llm,
        "vector_backends": vector_backends,
        "vector_active": vector_active,
        "vault_path": _vault_str(),
        "rag_dir": os.environ.get("RAG_DIR") or None,
        "config_path": str(_safe(config.config_path, default="")),
        "memory_params": {k: round(float(v), 4) for k, v in params.items()},
        "extensions": _extensions(),
    }


def _extensions() -> list[dict[str, Any]]:
    try:
        from eidetic_os import extensions as ext

        loaded = ext.discover() if hasattr(ext, "discover") else []
        out = []
        for e in loaded:
            out.append(
                {
                    "name": getattr(e, "name", str(e)),
                    "loaded": True,
                }
            )
        return out
    except Exception:
        return []


# ── 6. Backends (on-demand network probe) ─────────────────────────────────────
def backends_status(timeout: float = 1.5) -> dict[str, Any]:
    """Probe configured LLM backends. Slower (network) — its own endpoint."""
    from eidetic_os import backends

    out = []
    for status in _safe(lambda: backends.backend_statuses(timeout=timeout), default=[]):
        out.append(
            {
                "name": status.backend.name,
                "label": status.backend.label,
                "base_url": status.backend.base_url,
                "reachable": status.reachable,
                "models": list(status.models)[:8],
                "error": status.error,
            }
        )
    detected = _safe(lambda: backends.detect_backend(timeout=timeout), default=None)
    return {
        "backends": out,
        "detected": detected.name if detected is not None else None,
        "forced": os.environ.get("EIDETIC_LLM_BACKEND") or None,
    }


def _backend_summary() -> dict[str, Any]:
    """Config-only backend summary for the Overview (no network)."""
    forced = os.environ.get("EIDETIC_LLM_BACKEND") or None
    model = os.environ.get("EIDETIC_LLM_MODEL") or None
    return {
        "forced": forced,
        "model": model,
        "configured": forced or "auto-detect",
    }


# ── tiny utilities ────────────────────────────────────────────────────────────
def _vault_str() -> str | None:
    vault = os.environ.get("VAULT_PATH")
    return os.path.expanduser(vault) if vault else None


def _safe(fn: Any, *, default: Any) -> Any:
    """Call ``fn``; return ``default`` on any exception (never let the API 500)."""
    try:
        return fn()
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
