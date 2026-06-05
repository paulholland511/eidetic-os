"""Append-only audit trail for every autonomous Eidetic OS action.

Every command Eidetic runs on your behalf — embedding the vault, committing to
git, sending an email, generating a trading brief — appends one JSON object to
a tamper-evident log. This gives you a single, queryable record of *what* ran,
*how* it was triggered, *why*, and *what changed* — the kind of operational
logging ISO 27001 control A.12.4 asks for.

The log lives at ``$EIDETIC_AUDIT_PATH`` if set, otherwise
``$VAULT_PATH/.eidetic/audit.jsonl``, otherwise ``./.eidetic/audit.jsonl``.

Format
------
One JSON object per line (JSONL). Each entry has::

    {
      "timestamp": "2026-06-03T18:04:11.123456+00:00",  # ISO 8601, UTC
      "action": "commit",          # what ran
      "trigger": "scheduled",      # how: scheduled | manual | cli
      "status": "success",         # success | error | skipped
      "duration_seconds": 1.84,
      "changes": ["3 new", "1 modified"],   # what was modified/created/sent
      "context": "nightly schedule",        # why it ran
      "error": null                # traceback/message when status == "error"
    }

Concurrency
-----------
Appends are serialised with an in-process lock *and* an OS-level advisory file
lock (``fcntl.flock`` where available), so concurrent threads and separate
``eidetic`` processes never interleave a line.

Rotation
--------
When the active file would exceed ``MAX_BYTES`` (10 MB) it is rotated to
``audit.jsonl.1``; any existing ``.1`` becomes ``.2`` and so on, oldest last.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:  # POSIX advisory file locking (macOS + Linux). Optional by design.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

# 10 MB — comfortably holds tens of thousands of entries before rotating.
MAX_BYTES = 10 * 1024 * 1024

# Serialises appends within a single process; the file lock covers cross-process.
_LOCK = threading.Lock()

_VALID_STATUS = frozenset({"success", "error", "skipped"})


# ─────────────────────────────────────────────────────────────────────────────
# Path resolution
# ─────────────────────────────────────────────────────────────────────────────
def audit_path() -> Path:
    """Resolve the active audit log path from the environment.

    Order: ``EIDETIC_AUDIT_PATH`` → ``VAULT_PATH/.eidetic/audit.jsonl`` →
    ``./.eidetic/audit.jsonl``. Read fresh each call so tests and scheduled jobs
    can redirect it via the environment.
    """
    override = os.environ.get("EIDETIC_AUDIT_PATH")
    if override:
        return Path(os.path.expanduser(override))
    vault = os.environ.get("VAULT_PATH")
    base = Path(os.path.expanduser(vault)) if vault else Path.cwd()
    return base / ".eidetic" / "audit.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────
def _rotate_if_needed(path: Path, incoming_bytes: int) -> None:
    """Rotate ``audit.jsonl`` → ``.1`` → ``.2`` … if it would exceed MAX_BYTES.

    Called while the in-process lock is held. Shifts every existing numbered
    backup up by one so the lowest suffix is always the most recent rotation.
    """
    if not path.exists():
        return
    if path.stat().st_size + incoming_bytes <= MAX_BYTES:
        return

    # Find the highest existing backup index so we can shift from the top down.
    highest = 0
    for sibling in path.parent.glob(path.name + ".*"):
        suffix = sibling.name[len(path.name) + 1 :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))

    for index in range(highest, 0, -1):
        path.with_suffix(path.suffix + f".{index}").rename(
            path.with_suffix(path.suffix + f".{index + 1}")
        )
    path.rename(path.with_suffix(path.suffix + ".1"))


def log_action(
    action: str,
    trigger: str,
    status: str,
    changes: list[str] | None = None,
    context: str = "",
    error: str | None = None,
    duration: float | None = None,
) -> dict[str, Any]:
    """Append one audit entry and return the entry that was written.

    Parameters mirror the on-disk schema. ``status`` must be one of
    ``success``/``error``/``skipped``. Failures to write are swallowed and
    reported on stderr — auditing must never crash the action it is recording.
    """
    if status not in _VALID_STATUS:
        raise ValueError(
            f"status must be one of {sorted(_VALID_STATUS)}, got {status!r}"
        )

    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "trigger": trigger,
        "status": status,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "changes": list(changes) if changes else [],
        "context": context,
        "error": error,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    payload = line.encode("utf-8")

    path = audit_path()
    try:
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(path, len(payload))
            with path.open("ab") as handle:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                finally:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:  # pragma: no cover - disk/permission edge cases
        import sys

        print(f"audit: failed to write entry ({exc})", file=sys.stderr)

    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Reading / querying
# ─────────────────────────────────────────────────────────────────────────────
def _parse_since(since: str | datetime) -> datetime:
    """Coerce a ``since`` filter into an aware UTC datetime.

    Accepts a ``datetime``, a relative span (``30m``, ``24h``, ``7d``), or any
    ISO 8601 string (``2026-06-01`` or ``2026-06-01T12:00:00+00:00``).
    """
    if isinstance(since, datetime):
        return since if since.tzinfo else since.replace(tzinfo=timezone.utc)

    text = since.strip()
    if text and text[-1] in "smhdw" and text[:-1].isdigit():
        amount = int(text[:-1])
        unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[
            text[-1]
        ]
        return datetime.now(timezone.utc) - timedelta(**{unit: amount})

    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ordered_log_files(path: Path) -> list[Path]:
    """All log files oldest→newest: highest-numbered backup first, base last."""
    backups = []
    for sibling in path.parent.glob(path.name + ".*"):
        suffix = sibling.name[len(path.name) + 1 :]
        if suffix.isdigit():
            backups.append((int(suffix), sibling))
    ordered = [p for _, p in sorted(backups, reverse=True)]
    if path.exists():
        ordered.append(path)
    return ordered


def read_audit(
    since: str | datetime | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return audit entries (oldest→newest), most recent ``limit`` after filters.

    ``since`` keeps entries at or after the given time; ``action`` keeps only a
    matching action. Reads across rotated backups so historical queries work.
    Malformed lines are skipped rather than raising.
    """
    cutoff = _parse_since(since) if since is not None else None
    matched: list[dict[str, Any]] = []

    for log_file in _ordered_log_files(audit_path()):
        try:
            text = log_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if action is not None and entry.get("action") != action:
                continue
            if cutoff is not None:
                stamp = entry.get("timestamp")
                if not stamp:
                    continue
                try:
                    when = datetime.fromisoformat(stamp)
                except ValueError:
                    continue
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if when < cutoff:
                    continue
            matched.append(entry)

    if limit is not None and limit >= 0:
        return matched[-limit:]
    return matched
