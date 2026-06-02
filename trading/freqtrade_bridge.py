#!/usr/bin/env python3
"""
freqtrade_bridge.py
===================

Bridge between the TradingAgents SDK (4 analysts on LM Studio) and Freqtrade.

Pipeline:
    1. Find the most recent trading-briefing-YYYY-MM-DD.md in the vault.
    2. Parse the per-asset analyst votes (fundamentals / sentiment / news / technical).
    3. Hand the votes to a Portfolio Manager step — Claude Opus 4.6 by default,
       LM Studio as fallback — for final debate and synthesis.
    4. Write signals.json into Freqtrade's user_data so the strategy can read it.

Architecture:
    [LM Studio]  fundamentals + sentiment + news + technical  → briefing.md
                                                                    │
                                                                    ▼
    [Claude Opus 4.6 (PM)]  debate → final signal + confidence + reasoning
                                                                    │
                                                                    ▼
                                                          signals.json
                                                                    │
                                                                    ▼
                                                       Freqtrade strategy

Run:
    python freqtrade_bridge.py
    python freqtrade_bridge.py --dry-run        # don't write the output
    python freqtrade_bridge.py --no-pm          # skip the PM step, use briefing's existing recs
    python freqtrade_bridge.py --provider local # force LM Studio for PM step

Key lookup for Anthropic falls back through env → ~/.anthropic-api-key →
.env files in TradingAgents / Atlas / trading-sdk → `claude` CLI.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "freqtrade_bridge.config.json"

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

logger = logging.getLogger("freqtrade_bridge")


def setup_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AnalystVote:
    agent: str
    signal: str  # buy / sell / hold
    confidence: float


@dataclass(frozen=True)
class BriefingEntry:
    ticker: str
    headline_signal: str
    headline_confidence: float
    votes: list[AnalystVote]


@dataclass
class FinalSignal:
    signal: str  # buy / sell / hold
    confidence: float
    reasoning: str
    source: str  # "claude" | "local" | "briefing"
    votes: list[dict[str, Any]] = field(default_factory=list)
    stale: bool = False


# --------------------------------------------------------------------------- #
# Config + key resolution
# --------------------------------------------------------------------------- #


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _parse_env_file(path: Path) -> dict[str, str]:
    """Cheap .env parser — KEY=VALUE per line, ignores blanks and #."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("'").strip('"')
    return out


def resolve_anthropic_key(lookup_order: list[str]) -> tuple[str | None, str]:
    """Walk the configured lookup order and return (key, source_label)."""
    for entry in lookup_order:
        kind, _, target = entry.partition(":")
        if kind == "env":
            value = os.environ.get(target, "").strip()
            if value:
                return value, f"env:{target}"
        elif kind == "file":
            path = Path(os.path.expanduser(target))
            if path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value, f"file:{path}"
        elif kind == "envfile":
            path = Path(os.path.expanduser(target))
            env = _parse_env_file(path)
            value = env.get("ANTHROPIC_API_KEY", "").strip()
            if value:
                return value, f"envfile:{path}"
        elif kind == "cli":
            # `cli:` entries are not API keys — we hand them to the CLI fallback
            # path elsewhere. Skip during key resolution.
            continue
    return None, ""


def is_claude_cli_available() -> bool:
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# --------------------------------------------------------------------------- #
# Briefing discovery + parsing
# --------------------------------------------------------------------------- #

BRIEFING_FILE_RE = re.compile(r"^trading-briefing-(\d{4}-\d{2}-\d{2})\.md$")

# Summary table row, e.g.  | XRP-USD | HOLD | 70% | +17% | HOLD |
SUMMARY_ROW_RE = re.compile(
    r"^\|\s*([A-Z0-9\-]+)\s*\|\s*(BUY|SELL|HOLD)\s*\|\s*(\d+)%\s*\|",
    re.IGNORECASE,
)

# Per-ticker section header
TICKER_SECTION_RE = re.compile(r"^###\s+([A-Z0-9\-]+)\s*$")

# Votes line, e.g.  - fundamentals: HOLD (65%)
VOTE_LINE_RE = re.compile(
    r"^-\s*(fundamentals|sentiment|news|technical):\s*(BUY|SELL|HOLD)\s*\((\d+)%\)",
    re.IGNORECASE,
)


def find_latest_briefing(briefings_dir: Path) -> Path | None:
    candidates: list[tuple[str, Path]] = []
    for entry in briefings_dir.iterdir():
        match = BRIEFING_FILE_RE.match(entry.name)
        if match is not None:
            candidates.append((match.group(1), entry))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def briefing_age_hours(path: Path) -> float:
    match = BRIEFING_FILE_RE.match(path.name)
    if match is None:
        return 9999.0
    briefing_date = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    return (datetime.now(timezone.utc) - briefing_date).total_seconds() / 3600.0


def parse_briefing(briefing_path: Path) -> list[BriefingEntry]:
    text = briefing_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    headline: dict[str, tuple[str, float]] = {}
    for line in lines:
        match = SUMMARY_ROW_RE.match(line)
        if match is None:
            continue
        ticker, signal, confidence = match.groups()
        headline[ticker] = (signal.lower(), int(confidence) / 100.0)

    votes_by_ticker: dict[str, list[AnalystVote]] = {}
    current: str | None = None
    in_votes_block = False
    for line in lines:
        ticker_match = TICKER_SECTION_RE.match(line)
        if ticker_match is not None:
            current = ticker_match.group(1)
            in_votes_block = False
            votes_by_ticker.setdefault(current, [])
            continue
        if current is None:
            continue
        if line.strip().startswith("**Agent Votes:**"):
            in_votes_block = True
            continue
        if in_votes_block and (line.startswith("---") or line.startswith("### ")):
            in_votes_block = False
        if in_votes_block:
            vote_match = VOTE_LINE_RE.match(line.strip())
            if vote_match is not None:
                agent, signal, confidence = vote_match.groups()
                votes_by_ticker[current].append(
                    AnalystVote(
                        agent=agent.lower(),
                        signal=signal.lower(),
                        confidence=int(confidence) / 100.0,
                    )
                )

    entries: list[BriefingEntry] = []
    for ticker, (signal, confidence) in headline.items():
        entries.append(
            BriefingEntry(
                ticker=ticker,
                headline_signal=signal,
                headline_confidence=confidence,
                votes=votes_by_ticker.get(ticker, []),
            )
        )
    return entries


# --------------------------------------------------------------------------- #
# Portfolio Manager — Claude Opus 4.6 with fallbacks
# --------------------------------------------------------------------------- #


def _build_pm_user_prompt(entry: BriefingEntry) -> str:
    vote_block = "\n".join(
        f"- {v.agent}: {v.signal.upper()} ({int(v.confidence * 100)}%)"
        for v in entry.votes
    ) or "(no per-analyst votes recorded)"
    return (
        f"Asset: {entry.ticker}\n"
        f"Analyst reports:\n{vote_block}\n\n"
        f"Briefing's headline synthesis: {entry.headline_signal.upper()} "
        f"({int(entry.headline_confidence * 100)}%).\n\n"
        "Debate these reports. Where do they agree, where do they conflict, "
        "and which carries the most weight given current evidence? Return your "
        "final recommendation as strict JSON: "
        '{"signal":"buy|sell|hold","confidence":0.0-1.0,"reasoning":"..."}.'
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    # Strip code fences if present, then grab the first {...} blob.
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "")
    match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
    if match is None:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def call_claude_api(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
) -> str | None:
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("anthropic SDK not installed; install with `pip install anthropic`")
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Concatenate all text blocks in the response.
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts) if parts else None
    except Exception as exc:  # noqa: BLE001 — narrow logging is enough here
        logger.warning("Claude API call failed: %s", exc)
        return None


def call_claude_cli(
    system_prompt: str,
    user_prompt: str,
    model: str,
) -> str | None:
    """Use the local `claude` CLI as a fallback when no API key is available."""
    prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
    try:
        result = subprocess.run(
            ["claude", "--model", model, "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("claude CLI call failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.warning("claude CLI exited %d: %s", result.returncode, result.stderr[:200])
        return None
    return result.stdout


def call_local_pm(
    system_prompt: str,
    user_prompt: str,
    endpoint: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str | None:
    """OpenAI-compatible /v1/chat/completions against LM Studio."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    request = urllib.request.Request(
        url=f"{endpoint.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("LM Studio PM call failed: %s", exc)
        return None
    choices = body.get("choices") or []
    if not choices:
        return None
    return choices[0].get("message", {}).get("content")


def run_portfolio_manager(
    entry: BriefingEntry,
    pm_config: dict[str, Any],
    forced_provider: str | None,
) -> FinalSignal:
    """Try the configured provider, then fall back. Always returns *something*."""
    system_prompt: str = pm_config["system_prompt"]
    user_prompt = _build_pm_user_prompt(entry)

    provider = forced_provider or pm_config["provider"]

    # --- Provider chain --------------------------------------------------- #
    if provider == "claude":
        claude_cfg = pm_config["claude"]
        api_key, key_source = resolve_anthropic_key(claude_cfg["_key_lookup_order"])
        if api_key:
            logger.info("[%s] PM via Claude API (%s, key from %s)",
                        entry.ticker, claude_cfg["model"], key_source)
            raw = call_claude_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=claude_cfg["model"],
                max_tokens=claude_cfg["max_tokens"],
                temperature=claude_cfg["temperature"],
                api_key=api_key,
            )
            if raw is not None:
                parsed = _extract_json_object(raw)
                if parsed is not None:
                    return _coerce_signal(parsed, source="claude", votes=entry.votes)
        # Try CLI fallback before bailing to local.
        if is_claude_cli_available():
            logger.info("[%s] PM via `claude` CLI (no API key, model=%s)",
                        entry.ticker, claude_cfg["model"])
            raw = call_claude_cli(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=claude_cfg["model"],
            )
            if raw is not None:
                parsed = _extract_json_object(raw)
                if parsed is not None:
                    return _coerce_signal(parsed, source="claude-cli", votes=entry.votes)
        logger.warning("[%s] Claude path unavailable, falling back to LM Studio", entry.ticker)

    # --- LM Studio fallback ---------------------------------------------- #
    local_cfg = pm_config["local"]
    logger.info("[%s] PM via LM Studio (%s)", entry.ticker, local_cfg["endpoint"])
    raw = call_local_pm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        endpoint=local_cfg["endpoint"],
        model=local_cfg["model"],
        max_tokens=local_cfg["max_tokens"],
        temperature=local_cfg["temperature"],
    )
    if raw is not None:
        parsed = _extract_json_object(raw)
        if parsed is not None:
            return _coerce_signal(parsed, source="local", votes=entry.votes)

    # --- Last-resort: use the briefing's own headline --------------------- #
    logger.warning("[%s] All PM providers failed; using briefing headline", entry.ticker)
    return FinalSignal(
        signal=entry.headline_signal,
        confidence=entry.headline_confidence,
        reasoning="PM step unavailable — using briefing headline synthesis.",
        source="briefing",
        votes=[asdict(v) for v in entry.votes],
    )


def _coerce_signal(
    parsed: dict[str, Any],
    source: str,
    votes: list[AnalystVote],
) -> FinalSignal:
    signal = str(parsed.get("signal", "hold")).strip().lower()
    if signal not in {"buy", "sell", "hold"}:
        signal = "hold"
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    reasoning = str(parsed.get("reasoning", "")).strip()[:600]
    return FinalSignal(
        signal=signal,
        confidence=confidence,
        reasoning=reasoning,
        source=source,
        votes=[asdict(v) for v in votes],
    )


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def build_signals_payload(
    entries: list[BriefingEntry],
    ticker_to_pair: dict[str, str],
    pm_config: dict[str, Any],
    use_portfolio_manager: bool,
    forced_provider: str | None,
    stale: bool,
) -> dict[str, Any]:
    pairs: dict[str, dict[str, Any]] = {}
    for entry in entries:
        pair = ticker_to_pair.get(entry.ticker)
        if pair is None:
            continue
        if use_portfolio_manager and entry.votes:
            final = run_portfolio_manager(entry, pm_config, forced_provider)
        else:
            final = FinalSignal(
                signal=entry.headline_signal,
                confidence=entry.headline_confidence,
                reasoning="Briefing headline (PM step skipped).",
                source="briefing",
                votes=[asdict(v) for v in entry.votes],
            )
        final.stale = stale
        pairs[pair] = {
            "signal": final.signal,
            "confidence": round(final.confidence, 3),
            "reasoning": final.reasoning,
            "source": final.source,
            "ticker": entry.ticker,
            "votes": final.votes,
            "stale": final.stale,
        }
    return pairs


def write_signals(output_path: Path, pairs: dict[str, Any], meta: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "signals": pairs,
    }
    tmp = output_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(output_path)
    logger.info("Wrote %d signals -> %s", len(pairs), output_path)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="parse + synthesise but don't write")
    parser.add_argument("--no-pm", action="store_true", help="skip Portfolio Manager step")
    parser.add_argument(
        "--provider",
        choices=["claude", "local"],
        help="force PM provider (overrides config)",
    )
    args = parser.parse_args(argv)

    config = load_config()

    paths = config["paths"]
    log_file = Path(os.path.expanduser(paths["log_file"]))
    setup_logging(log_file)

    briefings_dir = Path(os.path.expanduser(paths["briefings_dir"]))
    signals_output = Path(os.path.expanduser(paths["signals_output"]))

    latest = find_latest_briefing(briefings_dir)
    if latest is None:
        logger.error("No trading-briefing-YYYY-MM-DD.md found in %s", briefings_dir)
        return 1

    age_hours = briefing_age_hours(latest)
    max_age = float(config["freshness"]["max_briefing_age_hours"])
    stale = age_hours > max_age
    logger.info(
        "Using briefing %s (age %.1fh, stale=%s)", latest.name, age_hours, stale
    )

    entries = parse_briefing(latest)
    logger.info("Parsed %d entries from briefing", len(entries))

    pairs = build_signals_payload(
        entries=entries,
        ticker_to_pair=config["ticker_to_pair"],
        pm_config=config["portfolio_manager"],
        use_portfolio_manager=not args.no_pm,
        forced_provider=args.provider,
        stale=stale,
    )

    meta = {
        "briefing_file": latest.name,
        "briefing_age_hours": round(age_hours, 2),
        "stale": stale,
        "pm_enabled": not args.no_pm,
        "pm_provider": args.provider or config["portfolio_manager"]["provider"],
        "pm_model": config["portfolio_manager"]["claude"]["model"]
        if (args.provider or config["portfolio_manager"]["provider"]) == "claude"
        else config["portfolio_manager"]["local"]["model"],
    }

    if args.dry_run:
        print(json.dumps({"meta": meta, "signals": pairs}, indent=2))
        return 0

    write_signals(signals_output, pairs, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
