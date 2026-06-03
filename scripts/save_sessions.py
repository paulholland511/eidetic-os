#!/usr/bin/env python3
"""
Save Claude Cowork chat transcripts to the vault as clean markdown session logs.

Cowork stores each session as a metadata file (``local_<id>.json``) plus a
sibling workspace directory holding the actual conversation transcript in the
standard Claude Code JSONL format
(``local_<id>/.claude/projects/<project>/<cli-session>.jsonl``). This script
walks that storage, and for every session in the requested window produces a
self-describing note under ``$VAULT_PATH/sessions/`` with frontmatter, an
extracted summary, the key actions taken, and the files that were modified.

Everything is derived **deterministically** from the local transcript — no LLM
call, no network. The note lives in your own private vault; the script itself
ships no session content.

A watermark in ``$VAULT_PATH/.atlas/last_session_save.txt`` records the latest
activity timestamp captured so far, so a plain ``save`` run only processes
sessions that are new or have changed since last time. Notes are keyed by
session id and overwritten in place, so re-running is idempotent.

Configuration is read from the environment — no hardcoded paths.

Environment variables:
    VAULT_PATH            Absolute path to the vault (required for save).
    CLAUDE_SESSIONS_DIR   Override the Cowork session store location. Defaults
                          to the macOS path
                          ``~/Library/Application Support/Claude/local-agent-mode-sessions``.

Usage:
    python save_sessions.py                 # new/changed sessions since last run
    python save_sessions.py --since 24h     # sessions active in the last 24h
    python save_sessions.py --all           # every session ever
    python save_sessions.py --list          # list recent sessions (no writes)
    python save_sessions.py --json          # machine-readable summary
    python save_sessions.py --sessions-dir PATH   # read from a custom store
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _bootstrap import ensure_atlas_os

ensure_atlas_os()
from atlas_os import scriptkit  # noqa: E402

# Default Cowork session store on macOS. Override with CLAUDE_SESSIONS_DIR.
_DEFAULT_SESSIONS_DIR = (
    "~/Library/Application Support/Claude/local-agent-mode-sessions"
)

# Tool names that create or change a file, mapped to the input key holding the
# path. Used to build the "Files Modified" list from the transcript.
_FILE_TOOLS: dict[str, str] = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


# ── Configuration ──────────────────────────────────────────────────────────────
def vault_path() -> Path:
    """The configured vault root (``VAULT_PATH``), expanded."""
    return Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()


def sessions_dir(override: str | None = None) -> Path:
    """Resolve the Cowork session store: ``--sessions-dir`` › env › macOS default."""
    raw = override or os.environ.get("CLAUDE_SESSIONS_DIR") or _DEFAULT_SESSIONS_DIR
    return Path(os.path.expanduser(raw))


def sessions_out_dir() -> Path:
    """Where session-log notes are written (``$VAULT_PATH/sessions``)."""
    return vault_path() / "sessions"


def watermark_path() -> Path:
    """The ``.atlas/last_session_save.txt`` watermark file under the vault."""
    return vault_path() / ".atlas" / "last_session_save.txt"


# ── Data model ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SessionMeta:
    """The bits of a session's ``local_<id>.json`` metadata that we render."""

    session_id: str
    title: str
    created_ms: int
    last_activity_ms: int
    model: str
    meta_file: Path
    cli_session_id: str = ""

    @property
    def created(self) -> datetime:
        return datetime.fromtimestamp(self.created_ms / 1000, tz=timezone.utc)

    @property
    def last_activity(self) -> datetime:
        return datetime.fromtimestamp(self.last_activity_ms / 1000, tz=timezone.utc)


@dataclass
class TranscriptStats:
    """What we extract from a session's JSONL transcript."""

    user_turns: int = 0
    assistant_turns: int = 0
    first_user_text: str = ""
    tool_counts: dict[str, int] = field(default_factory=dict)
    files_modified: list[str] = field(default_factory=list)

    @property
    def total_turns(self) -> int:
        return self.user_turns + self.assistant_turns

    @property
    def tools_used(self) -> int:
        return sum(self.tool_counts.values())


# ── Metadata discovery ───────────────────────────────────────────────────────────
def parse_metadata(meta_file: Path) -> SessionMeta | None:
    """Parse one ``local_<id>.json`` metadata file, or None if it's unusable."""
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    session_id = str(data.get("sessionId") or "").strip()
    if not session_id:
        return None
    created = _coerce_int(data.get("createdAt"))
    last_activity = _coerce_int(data.get("lastActivityAt")) or created
    title = str(data.get("title") or "").strip() or "Untitled session"
    return SessionMeta(
        session_id=session_id,
        title=title,
        created_ms=created,
        last_activity_ms=last_activity,
        model=str(data.get("model") or "").strip(),
        meta_file=meta_file,
        cli_session_id=str(data.get("cliSessionId") or "").strip(),
    )


def _coerce_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def discover_sessions(store: Path) -> list[SessionMeta]:
    """Find every session in the store, newest first, de-duplicated by id.

    Cowork sometimes records the same session under more than one wrapper
    directory; we keep the copy with the most recent activity.
    """
    if not store.is_dir():
        return []
    by_id: dict[str, SessionMeta] = {}
    for meta_file in store.rglob("local_*.json"):
        meta = parse_metadata(meta_file)
        if meta is None:
            continue
        existing = by_id.get(meta.session_id)
        if existing is None or meta.last_activity_ms > existing.last_activity_ms:
            by_id[meta.session_id] = meta
    return sorted(by_id.values(), key=lambda m: m.last_activity_ms, reverse=True)


def find_transcript(meta: SessionMeta) -> Path | None:
    """Locate the JSONL transcript for a session, or None if it isn't present.

    The workspace directory sits beside the metadata file with the same stem
    (``local_<id>``). The transcript is the JSONL under
    ``.claude/projects/<project>/`` — preferably the one named after the
    session id, otherwise the most recently modified candidate.
    """
    workspace = meta.meta_file.with_suffix("")
    projects = workspace / ".claude" / "projects"
    if not projects.is_dir():
        return None
    candidates = sorted(projects.glob("*/*.jsonl"))
    if not candidates:
        return None
    if meta.cli_session_id:
        for path in candidates:
            if path.stem == meta.cli_session_id:
                return path
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ── Transcript parsing ────────────────────────────────────────────────────────────
def _message_text(content: object) -> str:
    """Flatten a message ``content`` field (string or block list) to plain text."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text.strip())
    return "\n".join(p for p in parts if p).strip()


def _is_human_turn(content: object) -> bool:
    """True for a real human prompt (text), not a tool-result-only message."""
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "text" and b.get("text")
            for b in content
        )
    return False


def parse_transcript(path: Path) -> TranscriptStats:
    """Extract turn counts, tools used, files modified, and the opening ask.

    Tolerant of malformed lines: a bad JSONL record is skipped rather than
    aborting the whole transcript.
    """
    stats = TranscriptStats()
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return stats

    seen_files: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")

        if role == "user":
            if _is_human_turn(content):
                stats.user_turns += 1
                if not stats.first_user_text:
                    stats.first_user_text = _message_text(content)
        elif role == "assistant":
            stats.assistant_turns += 1

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name") or "").strip()
                if not name:
                    continue
                stats.tool_counts[name] = stats.tool_counts.get(name, 0) + 1
                key = _FILE_TOOLS.get(name)
                if key:
                    target = block.get("input")
                    fp = target.get(key) if isinstance(target, dict) else None
                    if isinstance(fp, str) and fp and fp not in seen_files:
                        seen_files.add(fp)
                        stats.files_modified.append(fp)
    return stats


# ── Formatting helpers ──────────────────────────────────────────────────────────
def slugify(text: str, max_len: int = 60) -> str:
    """Filesystem-safe kebab-case slug for a session title."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "session"


def human_duration(ms: int) -> str:
    """Render a millisecond span as a compact human duration."""
    seconds = max(0, ms) // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m" if sec == 0 else f"{minutes}m {sec}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h" if mins == 0 else f"{hours}h {mins}m"


def clean_tool_name(name: str) -> str:
    """Make an MCP tool name readable: ``mcp__server__do_thing`` → ``do_thing (server)``."""
    if name.startswith("mcp__"):
        parts = name.split("__")
        if len(parts) >= 3:
            return f"{parts[-1]} ({parts[1]})"
        return parts[-1]
    return name


def _truncate(text: str, limit: int = 280) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def note_filename(meta: SessionMeta) -> str:
    """``session-log-YYYY-MM-DD-<slug>.md`` for a session."""
    date = meta.created.astimezone().strftime("%Y-%m-%d")
    return f"session-log-{date}-{slugify(meta.title)}.md"


def build_key_actions(stats: TranscriptStats) -> list[str]:
    """Human-readable bullets summarising what the session did."""
    actions: list[str] = []
    if stats.user_turns:
        actions.append(f"{stats.user_turns} request(s) over {stats.total_turns} message(s)")
    edits = sum(stats.tool_counts.get(t, 0) for t in ("Write", "Edit", "MultiEdit", "NotebookEdit"))
    if edits:
        actions.append(f"{edits} file edit(s) across {len(stats.files_modified)} file(s)")
    if stats.tool_counts.get("Bash"):
        actions.append(f"Ran {stats.tool_counts['Bash']} shell command(s)")
    searches = stats.tool_counts.get("WebSearch", 0) + stats.tool_counts.get("WebFetch", 0)
    if searches:
        actions.append(f"{searches} web search/fetch(es)")
    # The handful of most-used tools, cleaned for readability.
    if stats.tool_counts:
        top = sorted(stats.tool_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
        rendered = ", ".join(f"{clean_tool_name(n)} ×{c}" for n, c in top)
        actions.append(f"Tools used: {rendered}")
    if not actions:
        actions.append("No recorded actions (empty or metadata-only session)")
    return actions


def build_note(meta: SessionMeta, stats: TranscriptStats) -> str:
    """Render the full markdown note for a session."""
    local_created = meta.created.astimezone()
    date = local_created.strftime("%Y-%m-%d")
    when = local_created.strftime("%Y-%m-%d %H:%M")
    duration = human_duration(meta.last_activity_ms - meta.created_ms)
    title = meta.title.replace('"', "'")

    if stats.first_user_text:
        summary = (
            f"The session opened with: \"{_truncate(stats.first_user_text)}\" "
            f"It ran for {duration} across {stats.total_turns} message(s), "
            f"using {stats.tools_used} tool call(s)."
        )
    elif stats.total_turns:
        summary = (
            f"A {duration} session across {stats.total_turns} message(s), "
            f"using {stats.tools_used} tool call(s)."
        )
    else:
        summary = (
            "No transcript was available for this session — only metadata "
            "(title, timestamps, model) was captured."
        )

    lines = [
        "---",
        f'title: "Session: {title}"',
        f"date: {date}",
        "tags: [session-log, cowork]",
        f"session_id: {meta.session_id}",
        "---",
        "",
        f"# {meta.title}",
        "",
        f"**Date:** {when}",
        f"**Duration:** {duration}",
        f"**Tasks completed:** {stats.user_turns}",
    ]
    if meta.model:
        lines.append(f"**Model:** {meta.model}")
    lines += [
        "",
        "## Summary",
        summary,
        "",
        "## Key Actions",
    ]
    lines += [f"- {action}" for action in build_key_actions(stats)]
    lines += ["", "## Files Modified"]
    if stats.files_modified:
        lines += [f"- `{path}`" for path in stats.files_modified]
    else:
        lines.append("- _None recorded._")
    lines.append("")
    return "\n".join(lines)


# ── Watermark ──────────────────────────────────────────────────────────────────
def read_watermark() -> int:
    """Last captured ``lastActivityAt`` (ms), or 0 if no prior run."""
    path = watermark_path()
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def write_watermark(value_ms: int) -> None:
    """Persist the watermark, never moving it backwards."""
    path = watermark_path()
    current = read_watermark()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(str(max(current, value_ms)), encoding="utf-8")
    except OSError:
        pass


def since_cutoff_ms(spec: str) -> int:
    """Convert a ``--since`` spec (``24h``, ``7d``, ISO date) to an epoch-ms cutoff."""
    text = spec.strip()
    if text and text[-1] in "smhdw" and text[:-1].isdigit():
        unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[
            text[-1]
        ]
        cutoff = datetime.now(timezone.utc) - timedelta(**{unit: int(text[:-1])})
    else:
        parsed = datetime.fromisoformat(text)
        cutoff = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return int(cutoff.timestamp() * 1000)


def select_sessions(
    sessions: list[SessionMeta], *, since: str | None, capture_all: bool
) -> list[SessionMeta]:
    """Filter discovered sessions by the requested window."""
    if capture_all:
        return sessions
    cutoff = since_cutoff_ms(since) if since else read_watermark()
    return [s for s in sessions if s.last_activity_ms > cutoff]


# ── Save ──────────────────────────────────────────────────────────────────────
def save_session(meta: SessionMeta, out_dir: Path, used: set[str]) -> Path:
    """Write one session's note, disambiguating filename collisions."""
    name = note_filename(meta)
    if name in used:
        stem, ext = name.rsplit(".", 1)
        name = f"{stem}-{meta.session_id[-8:]}.{ext}"
    used.add(name)
    transcript = find_transcript(meta)
    stats = parse_transcript(transcript) if transcript else TranscriptStats()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / name
    dest.write_text(build_note(meta, stats), encoding="utf-8")
    return dest


def run_save(
    *, since: str | None, capture_all: bool, override_dir: str | None
) -> dict[str, object]:
    """Capture the selected sessions to the vault; return a summary dict."""
    store = sessions_dir(override_dir)
    discovered = discover_sessions(store)
    selected = select_sessions(discovered, since=since, capture_all=capture_all)

    out_dir = sessions_out_dir()
    used: set[str] = set()
    saved: list[str] = []
    for meta in selected:
        dest = save_session(meta, out_dir, used)
        saved.append(str(dest))

    if discovered:
        write_watermark(max(s.last_activity_ms for s in discovered))

    return {
        "store": str(store),
        "discovered": len(discovered),
        "new": len(saved),
        "saved": saved,
        "out_dir": str(out_dir),
    }


def run_list(override_dir: str | None, limit: int) -> list[SessionMeta]:
    """Return the most recent sessions for the ``list`` view."""
    return discover_sessions(sessions_dir(override_dir))[:limit]


# ── Output ──────────────────────────────────────────────────────────────────────
def print_list(sessions: list[SessionMeta], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps({
            "sessions": [
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "date": s.created.astimezone().strftime("%Y-%m-%d %H:%M"),
                    "model": s.model,
                }
                for s in sessions
            ],
            "count": len(sessions),
        }, indent=2))
        return
    if not sessions:
        print("No Cowork sessions found.")
        return
    print(f"\nRecent Cowork sessions ({len(sessions)}):\n")
    for s in sessions:
        when = s.created.astimezone().strftime("%Y-%m-%d %H:%M")
        print(f"  {when}  {s.title}")


def print_save(summary: dict[str, object], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(summary, indent=2))
        return
    new = summary["new"]
    if new:
        print(f"\nCaptured {new} session(s) → {summary['out_dir']}")
        for path in summary["saved"]:  # type: ignore[union-attr]
            print(f"  + {Path(str(path)).name}")
    else:
        print(
            f"\nNo new sessions to capture "
            f"({summary['discovered']} found in {summary['store']})."
        )


# ── Entry point ──────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Save Cowork sessions to the vault")
    parser.add_argument("--since", help="Capture sessions active since e.g. 24h, 7d, 2026-06-01")
    parser.add_argument("--all", action="store_true", dest="capture_all", help="Capture every session")
    parser.add_argument("--list", action="store_true", dest="list_only", help="List recent sessions; do not write")
    parser.add_argument("--limit", type=int, default=20, help="Max sessions for --list")
    parser.add_argument("--sessions-dir", dest="sessions_dir", help="Override the Cowork session store path")
    parser.add_argument("--json", action="store_true", dest="json_out", help="JSON output")
    args = parser.parse_args()

    if args.list_only:
        print_list(run_list(args.sessions_dir, args.limit), args.json_out)
        return

    if not os.environ.get("VAULT_PATH"):
        scriptkit.fail(
            "VAULT_PATH environment variable is not set. See .env.example.",
            code=scriptkit.EXIT_CONFIG,
            json_mode=args.json_out,
        )

    try:
        cutoff_check = args.since
        if cutoff_check:
            since_cutoff_ms(cutoff_check)  # validate early for a clean message
    except ValueError as exc:
        scriptkit.fail(f"bad --since value: {exc}", code=scriptkit.EXIT_CONFIG, json_mode=args.json_out)

    summary = run_save(
        since=args.since, capture_all=args.capture_all, override_dir=args.sessions_dir
    )
    print_save(summary, args.json_out)


if __name__ == "__main__":
    with scriptkit.error_boundary(json_mode=scriptkit.json_mode_requested()):
        main()
