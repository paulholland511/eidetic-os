"""Tests for scripts/save_sessions.py — Cowork session capture.

All fixtures are synthetic: no real session content or PII ever touches the test
suite. Each test builds a throwaway session store and points the script at it
with ``--sessions-dir`` / ``CLAUDE_SESSIONS_DIR`` and a temp ``VAULT_PATH``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import save_sessions as ss


# ── Synthetic store builder ──────────────────────────────────────────────────────
def _write_session(
    store: Path,
    *,
    session_id: str,
    title: str,
    created_ms: int,
    last_activity_ms: int,
    cli_session_id: str = "cli-1",
    model: str = "claude-opus-4-8",
    transcript_lines: list[dict] | None = None,
) -> Path:
    """Create one metadata file (+ optional transcript) under ``store``."""
    meta_file = store / f"{session_id}.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(
        json.dumps({
            "sessionId": session_id,
            "cliSessionId": cli_session_id,
            "title": title,
            "createdAt": created_ms,
            "lastActivityAt": last_activity_ms,
            "model": model,
        }),
        encoding="utf-8",
    )
    if transcript_lines is not None:
        tdir = store / session_id / ".claude" / "projects" / "proj"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{cli_session_id}.jsonl").write_text(
            "\n".join(json.dumps(line) for line in transcript_lines),
            encoding="utf-8",
        )
    return meta_file


def _sample_transcript() -> list[dict]:
    return [
        {"type": "user", "message": {"role": "user", "content": "Add a CSV exporter and run tests."}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "On it."},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/proj/export.py"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/proj/export.py"}},
            {"type": "tool_use", "name": "mcp__github__create_commit", "input": {}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": "Thanks, commit it."}},
    ]


@pytest.fixture()
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    v = tmp_path / "vault"
    (v / ".atlas").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VAULT_PATH", str(v))
    return v


# ── Pure formatting helpers ──────────────────────────────────────────────────────
class TestHelpers:
    def test_slugify(self) -> None:
        assert ss.slugify("Build a Widget Exporter!") == "build-a-widget-exporter"
        assert ss.slugify("   ") == "session"
        assert len(ss.slugify("x" * 200)) <= 60

    def test_human_duration(self) -> None:
        assert ss.human_duration(5_000) == "5s"
        assert ss.human_duration(600_000) == "10m"
        assert ss.human_duration(90_000) == "1m 30s"
        assert ss.human_duration(3_600_000) == "1h"
        assert ss.human_duration(5_400_000) == "1h 30m"
        assert ss.human_duration(-10) == "0s"

    def test_clean_tool_name(self) -> None:
        assert ss.clean_tool_name("Bash") == "Bash"
        assert ss.clean_tool_name("mcp__github__create_commit") == "create_commit (github)"
        assert ss.clean_tool_name("mcp__server") == "server"

    def test_since_cutoff_relative_and_iso(self) -> None:
        # Relative spans return a cutoff strictly in the past.
        import time
        now_ms = int(time.time() * 1000)
        assert ss.since_cutoff_ms("24h") < now_ms
        assert ss.since_cutoff_ms("7d") < ss.since_cutoff_ms("24h")
        # ISO date parses to a fixed epoch.
        assert ss.since_cutoff_ms("2026-01-01") > 0

    def test_since_cutoff_bad_value(self) -> None:
        with pytest.raises(ValueError):
            ss.since_cutoff_ms("not-a-date")


# ── Metadata parsing ──────────────────────────────────────────────────────────────
class TestParseMetadata:
    def test_valid(self, tmp_path: Path) -> None:
        meta_file = _write_session(
            tmp_path, session_id="local_a", title="Hello",
            created_ms=1_700_000_000_000, last_activity_ms=1_700_000_060_000,
        )
        meta = ss.parse_metadata(meta_file)
        assert meta is not None
        assert meta.session_id == "local_a"
        assert meta.title == "Hello"
        assert meta.cli_session_id == "cli-1"

    def test_missing_session_id_is_none(self, tmp_path: Path) -> None:
        bad = tmp_path / "local_bad.json"
        bad.write_text(json.dumps({"title": "no id"}), encoding="utf-8")
        assert ss.parse_metadata(bad) is None

    def test_malformed_json_is_none(self, tmp_path: Path) -> None:
        bad = tmp_path / "local_bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert ss.parse_metadata(bad) is None

    def test_blank_title_defaults(self, tmp_path: Path) -> None:
        meta_file = _write_session(
            tmp_path, session_id="local_a", title="",
            created_ms=1_700_000_000_000, last_activity_ms=1_700_000_000_000,
        )
        meta = ss.parse_metadata(meta_file)
        assert meta is not None and meta.title == "Untitled session"


# ── Transcript parsing ──────────────────────────────────────────────────────────────
class TestParseTranscript:
    def test_extracts_turns_tools_and_files(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            "\n".join(json.dumps(line) for line in _sample_transcript()),
            encoding="utf-8",
        )
        stats = ss.parse_transcript(path)
        assert stats.user_turns == 2  # tool-result-only user message excluded
        assert stats.assistant_turns == 2
        assert stats.first_user_text.startswith("Add a CSV exporter")
        assert stats.tool_counts["Write"] == 1
        assert stats.tool_counts["Bash"] == 1
        assert stats.files_modified == ["/proj/export.py"]  # de-duplicated
        assert stats.tools_used == 4

    def test_tolerates_malformed_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            '{"type":"user","message":{"role":"user","content":"hi"}}\n'
            "this is not json\n"
            "\n"
            '{"type":"assistant","message":{"role":"assistant","content":[]}}\n',
            encoding="utf-8",
        )
        stats = ss.parse_transcript(path)
        assert stats.user_turns == 1
        assert stats.assistant_turns == 1

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        stats = ss.parse_transcript(tmp_path / "nope.jsonl")
        assert stats.total_turns == 0


# ── Discovery & transcript location ──────────────────────────────────────────────
class TestDiscovery:
    def test_dedupes_keeping_newest(self, tmp_path: Path) -> None:
        store = tmp_path / "store"
        _write_session(store / "a", session_id="local_dup", title="old",
                       created_ms=1000, last_activity_ms=2000)
        _write_session(store / "b", session_id="local_dup", title="new",
                       created_ms=1000, last_activity_ms=9000)
        sessions = ss.discover_sessions(store)
        assert len(sessions) == 1
        assert sessions[0].title == "new"

    def test_sorted_newest_first(self, tmp_path: Path) -> None:
        store = tmp_path / "store"
        _write_session(store, session_id="local_1", title="older",
                       created_ms=1000, last_activity_ms=1000)
        _write_session(store, session_id="local_2", title="newer",
                       created_ms=1000, last_activity_ms=5000)
        sessions = ss.discover_sessions(store)
        assert [s.title for s in sessions] == ["newer", "older"]

    def test_missing_store_is_empty(self, tmp_path: Path) -> None:
        assert ss.discover_sessions(tmp_path / "nope") == []

    def test_find_transcript_matches_cli_session_id(self, tmp_path: Path) -> None:
        store = tmp_path / "store"
        _write_session(store, session_id="local_a", title="t", created_ms=1, last_activity_ms=2,
                       cli_session_id="cli-xyz", transcript_lines=_sample_transcript())
        meta = ss.discover_sessions(store)[0]
        found = ss.find_transcript(meta)
        assert found is not None and found.stem == "cli-xyz"

    def test_find_transcript_absent(self, tmp_path: Path) -> None:
        store = tmp_path / "store"
        _write_session(store, session_id="local_a", title="t",
                       created_ms=1, last_activity_ms=2)  # no transcript_lines
        meta = ss.discover_sessions(store)[0]
        assert ss.find_transcript(meta) is None


# ── Watermark ──────────────────────────────────────────────────────────────────────
class TestWatermark:
    def test_round_trip_and_no_backwards(self, vault: Path) -> None:
        assert ss.read_watermark() == 0
        ss.write_watermark(5000)
        assert ss.read_watermark() == 5000
        ss.write_watermark(3000)  # older — must not move the watermark back
        assert ss.read_watermark() == 5000


# ── Selection ──────────────────────────────────────────────────────────────────────
class TestSelect:
    def _sessions(self) -> list[ss.SessionMeta]:
        return [
            ss.SessionMeta("local_old", "old", 1000, 1000, "m", Path("x")),
            ss.SessionMeta("local_new", "new", 9000, 9000, "m", Path("y")),
        ]

    def test_all_returns_everything(self) -> None:
        out = ss.select_sessions(self._sessions(), since=None, capture_all=True)
        assert len(out) == 2

    def test_since_iso_filters(self) -> None:
        # Cutoff between the two activity timestamps (epoch-ms 1000 vs 9000).
        sessions = self._sessions()
        out = ss.select_sessions(sessions, since="1970-01-01T00:00:05+00:00", capture_all=False)
        assert [s.session_id for s in out] == ["local_new"]

    def test_watermark_default(self, vault: Path) -> None:
        ss.write_watermark(5000)
        out = ss.select_sessions(self._sessions(), since=None, capture_all=False)
        assert [s.session_id for s in out] == ["local_new"]


# ── Note rendering ──────────────────────────────────────────────────────────────────
class TestBuildNote:
    def test_frontmatter_and_sections(self) -> None:
        meta = ss.SessionMeta("local_a", 'Title "quoted"', 1_700_000_000_000,
                              1_700_000_600_000, "claude-opus-4-8", Path("x"))
        stats = ss.TranscriptStats(
            user_turns=2, assistant_turns=2, first_user_text="Do the thing.",
            tool_counts={"Write": 1, "Bash": 2}, files_modified=["/a.py"],
        )
        note = ss.build_note(meta, stats)
        assert note.startswith("---\n")
        assert "tags: [session-log, cowork]" in note
        assert "session_id: local_a" in note
        assert 'title: "Session: Title \'quoted\'"' in note  # quotes neutralised
        assert "**Tasks completed:** 2" in note
        assert "## Summary" in note and "Do the thing." in note
        assert "## Key Actions" in note
        assert "## Files Modified" in note and "`/a.py`" in note

    def test_metadata_only_note(self) -> None:
        meta = ss.SessionMeta("local_a", "t", 1_700_000_000_000,
                              1_700_000_000_000, "", Path("x"))
        note = ss.build_note(meta, ss.TranscriptStats())
        assert "No transcript was available" in note
        assert "_None recorded._" in note

    def test_note_filename(self) -> None:
        meta = ss.SessionMeta("local_a", "Build It", 1_700_000_000_000,
                              1_700_000_000_000, "m", Path("x"))
        name = ss.note_filename(meta)
        assert name.startswith("session-log-") and name.endswith("-build-it.md")


# ── End-to-end save ──────────────────────────────────────────────────────────────────
class TestRunSave:
    def test_save_then_idempotent(self, tmp_path: Path, vault: Path) -> None:
        store = tmp_path / "store"
        _write_session(store, session_id="local_a", title="Widget work",
                       created_ms=1_700_000_000_000, last_activity_ms=1_700_000_600_000,
                       transcript_lines=_sample_transcript())

        summary = ss.run_save(since=None, capture_all=True, override_dir=str(store))
        assert summary["new"] == 1
        notes = list((vault / "sessions").glob("*.md"))
        assert len(notes) == 1
        assert "Widget work" in notes[0].read_text(encoding="utf-8")

        # Watermark advanced → a default re-run captures nothing new.
        again = ss.run_save(since=None, capture_all=False, override_dir=str(store))
        assert again["new"] == 0

    def test_filename_collision_disambiguated(self, tmp_path: Path, vault: Path) -> None:
        store = tmp_path / "store"
        # Two distinct sessions, same title and same calendar day.
        _write_session(store / "a", session_id="local_aaaaaaaa", title="Same Title",
                       created_ms=1_700_000_000_000, last_activity_ms=1_700_000_001_000)
        _write_session(store / "b", session_id="local_bbbbbbbb", title="Same Title",
                       created_ms=1_700_000_000_000, last_activity_ms=1_700_000_002_000)
        summary = ss.run_save(since=None, capture_all=True, override_dir=str(store))
        assert summary["new"] == 2
        assert len(list((vault / "sessions").glob("*.md"))) == 2  # no overwrite
