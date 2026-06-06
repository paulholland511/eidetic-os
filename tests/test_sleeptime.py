"""Tests for eidetic_os.sleeptime — the sleeptime consolidation daemon.

Covers the pure extraction heuristics, contradiction detection, note rendering,
session scanning with watermark tracking, and the end-to-end ``run_once`` pass.
Everything runs offline (no LLM backend, no network).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eidetic_os import sleeptime
from eidetic_os.frontmatter import validate_text
from eidetic_os.sleeptime import (
    ConsolidatedNote,
    ConsolidationDaemon,
    SessionTakeaways,
    detect_contradictions,
    extract_actions,
    extract_decisions,
    extract_files,
    extract_questions,
    extract_topics,
    heuristic_takeaways,
    merge_takeaways,
    render_note,
    strip_noise,
)


def _session_log(
    title: str,
    body: str,
    *,
    date: str = "2026-06-05",
) -> str:
    """Build a minimal session-log note matching the save_sessions template."""
    return (
        "---\n"
        f'title: "Session: {title}"\n'
        f"date: {date}\n"
        "tags: [session-log, cowork]\n"
        "---\n\n"
        f"# {title}\n\n"
        f"{body}\n"
    )


# ── Noise stripping ────────────────────────────────────────────────────────────


class TestStripNoise:
    def test_removes_code_fences(self) -> None:
        text = "Real prose.\n```\nsecret = 1\nrm -rf /\n```\nMore prose."
        cleaned = strip_noise(text)
        assert "Real prose." in cleaned
        assert "More prose." in cleaned
        assert "secret = 1" not in cleaned

    def test_removes_tracebacks_and_logs(self) -> None:
        text = (
            "We fixed the bug.\n"
            "Traceback (most recent call last):\n"
            '  File "x.py", line 3, in <module>\n'
            "ERROR something exploded\n"
            "Then we moved on."
        )
        cleaned = strip_noise(text)
        assert "We fixed the bug." in cleaned
        assert "Then we moved on." in cleaned
        assert "Traceback" not in cleaned
        assert "ERROR something exploded" not in cleaned

    def test_collapses_repeated_lines(self) -> None:
        text = "repeat me\nrepeat me\nrepeat me\nunique"
        cleaned = strip_noise(text)
        assert cleaned.count("repeat me") == 1
        assert "unique" in cleaned


# ── Heuristic extraction ───────────────────────────────────────────────────────


class TestExtraction:
    def test_extract_decisions(self) -> None:
        text = (
            "We decided to use Postgres for the store.\n"
            "Going with Typer for the CLI.\n"
            "Nothing interesting here."
        )
        decisions = extract_decisions(text)
        assert any("Postgres" in d for d in decisions)
        assert any("Typer" in d for d in decisions)
        assert len(decisions) == 2

    def test_extract_actions(self) -> None:
        text = (
            "Created the sleeptime module.\n"
            "Fixed the watermark bug.\n"
            "Pushed to main."
        )
        actions = extract_actions(text)
        assert len(actions) == 3
        assert any("sleeptime module" in a for a in actions)

    def test_extract_files(self) -> None:
        text = "Edited eidetic_os/sleeptime.py and docs/README.md plus config.toml."
        files = extract_files(text)
        assert "eidetic_os/sleeptime.py" in files
        assert "docs/README.md" in files
        assert "config.toml" in files

    def test_extract_topics_drops_boilerplate(self) -> None:
        text = (
            "# Consolidation Design\n"
            "## Summary\n"
            "some text\n"
            "## Caching Strategy\n"
            "more text\n"
            "## Files Modified\n"
        )
        topics = extract_topics(text)
        assert "Consolidation Design" in topics
        assert "Caching Strategy" in topics
        assert "Summary" not in topics
        assert "Files Modified" not in topics

    def test_extract_questions(self) -> None:
        text = "Should we cache embeddings? Yes. What about TTL? Unsure."
        questions = extract_questions(text)
        assert any("cache embeddings" in q for q in questions)
        assert all(q.endswith("?") for q in questions)

    def test_heuristic_takeaways_end_to_end(self) -> None:
        note = _session_log(
            "Build the daemon",
            "We decided to use threading for the loop.\n"
            "Created eidetic_os/sleeptime.py.\n"
            "## Locking\n"
            "Should the lock be advisory?\n"
            "```\nignored = True\n```",
        )
        takeaways = heuristic_takeaways(note, "session-log-1.md")
        assert takeaways.session_file == "session-log-1.md"
        assert any("threading" in d for d in takeaways.decisions)
        assert any("sleeptime.py" in a for a in takeaways.actions)
        assert "eidetic_os/sleeptime.py" in takeaways.files_touched
        assert "Locking" in takeaways.topics
        assert any("advisory" in q for q in takeaways.questions)
        assert not takeaways.is_empty


# ── Contradiction detection ────────────────────────────────────────────────────


class TestContradictions:
    def test_cross_session_conflict_keeps_recent(self) -> None:
        ordered = [
            ("session-1.md", "use SQLite for storage"),
            ("session-2.md", "use Postgres for storage"),
        ]
        contradictions = detect_contradictions(ordered)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert "SQLite" in c["old_fact"]
        assert "Postgres" in c["new_fact"]
        assert "Postgres" in c["resolution"]

    def test_no_conflict_when_purpose_differs(self) -> None:
        ordered = [
            ("session-1.md", "use SQLite for storage"),
            ("session-2.md", "use Redis for caching"),
        ]
        assert detect_contradictions(ordered) == []

    def test_inline_replacement(self) -> None:
        ordered = [("session-1.md", "use Ruff instead of Flake8")]
        contradictions = detect_contradictions(ordered)
        assert len(contradictions) == 1
        assert contradictions[0]["old_fact"] == "Flake8"
        assert contradictions[0]["new_fact"] == "Ruff"

    def test_same_choice_is_not_a_contradiction(self) -> None:
        ordered = [
            ("session-1.md", "use Postgres for storage"),
            ("session-2.md", "use Postgres for storage"),
        ]
        assert detect_contradictions(ordered) == []


# ── Merge + render ──────────────────────────────────────────────────────────────


class TestMergeAndRender:
    def test_merge_dedupes_and_resolves(self) -> None:
        takeaways = [
            SessionTakeaways(
                session_file="s1.md",
                decisions=["use SQLite for storage"],
                actions=["created module"],
                topics=["Design"],
                files_touched=["a.py"],
            ),
            SessionTakeaways(
                session_file="s2.md",
                decisions=["use Postgres for storage"],
                actions=["created module"],  # duplicate action
                topics=["Design"],  # duplicate topic
                files_touched=["b.py"],
            ),
        ]
        note = merge_takeaways(takeaways, date="2026-06-06")
        assert note.sessions_processed == ["s1.md", "s2.md"]
        assert note.actions == ["created module"]  # deduped
        assert note.topics == ["Design"]  # deduped
        assert set(note.files_touched) == {"a.py", "b.py"}
        assert len(note.contradictions) == 1
        # The superseded decision is dropped from the live list.
        assert not any("SQLite" in d for d in note.decisions)
        assert any("Postgres" in d for d in note.decisions)

    def test_render_note_frontmatter_is_valid(self) -> None:
        note = ConsolidatedNote(
            date="2026-06-06",
            sessions_processed=["s1.md"],
            decisions=["use Typer for the CLI"],
            actions=["wrote sleeptime.py"],
            topics=["Daemon"],
            files_touched=["eidetic_os/sleeptime.py"],
            summary="A short summary.",
            contradictions=[
                {"old_fact": "X", "new_fact": "Y", "resolution": "kept Y"}
            ],
            questions=["Is it done?"],
        )
        rendered = render_note(note)
        # Frontmatter must pass the same gate every automated commit uses.
        result = validate_text(rendered)
        assert result.ok, result.errors
        assert "type: consolidated" in rendered
        assert "## Contradictions Resolved" in rendered
        assert "eidetic_os/sleeptime.py" in rendered

    def test_render_empty_sections(self) -> None:
        note = ConsolidatedNote(
            date="2026-06-06",
            sessions_processed=[],
            decisions=[],
            actions=[],
            topics=[],
            files_touched=[],
            summary="Nothing happened.",
        )
        rendered = render_note(note)
        assert "_None recorded._" in rendered
        assert "_None detected._" in rendered
        assert validate_text(rendered).ok


# ── Watermark + scanning ────────────────────────────────────────────────────────


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "sessions").mkdir(parents=True)
    return vault


class TestScanning:
    def test_scan_empty_vault(self, tmp_path: Path) -> None:
        daemon = ConsolidationDaemon(tmp_path / "nope")
        assert daemon.scan_recent_sessions() == []

    def test_scan_finds_session_logs(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        (vault / "sessions" / "session-log-2026-06-05-a.md").write_text(
            _session_log("A", "Created a.py."), encoding="utf-8"
        )
        (vault / "sessions" / "not-a-session.md").write_text("ignore", encoding="utf-8")
        daemon = ConsolidationDaemon(vault)
        found = daemon.scan_recent_sessions()
        assert len(found) == 1
        assert found[0].name == "session-log-2026-06-05-a.md"

    def test_watermark_filters_old_sessions(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        old = vault / "sessions" / "session-log-2026-06-01-old.md"
        old.write_text(_session_log("Old", "Created old.py."), encoding="utf-8")
        daemon = ConsolidationDaemon(vault)

        # Set the watermark to "now" so the existing log is in the past.
        daemon.write_last_consolidation(datetime.now(timezone.utc))
        time.sleep(0.01)
        assert daemon.scan_recent_sessions() == []

        # A newer log appears after the watermark.
        new = vault / "sessions" / "session-log-2026-06-07-new.md"
        new.write_text(_session_log("New", "Created new.py."), encoding="utf-8")
        found = daemon.scan_recent_sessions()
        assert len(found) == 1
        assert found[0].name == new.name

    def test_watermark_roundtrip(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        daemon = ConsolidationDaemon(vault)
        assert daemon.read_last_consolidation() is None
        when = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
        daemon.write_last_consolidation(when)
        assert daemon.read_last_consolidation() == when

    def test_corrupt_watermark_is_none(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        daemon = ConsolidationDaemon(vault)
        daemon.watermark_path.parent.mkdir(parents=True, exist_ok=True)
        daemon.watermark_path.write_text("not a date", encoding="utf-8")
        assert daemon.read_last_consolidation() is None


# ── run_once end-to-end ─────────────────────────────────────────────────────────


class TestRunOnce:
    def test_missing_vault_is_noop(self, tmp_path: Path) -> None:
        daemon = ConsolidationDaemon(tmp_path / "absent", use_llm=False)
        assert daemon.run_once() is None

    def test_no_sessions_is_noop_but_sets_watermark(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        daemon = ConsolidationDaemon(vault, use_llm=False)
        assert daemon.run_once() is None
        assert daemon.read_last_consolidation() is not None

    def test_full_pass_writes_note(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        sessions = vault / "sessions"
        first = sessions / "session-log-2026-06-05-first.md"
        first.write_text(
            _session_log(
                "First",
                "We decided to use SQLite for storage.\nCreated eidetic_os/db.py.",
            ),
            encoding="utf-8",
        )
        # Ensure deterministic ordering: second is newer.
        time.sleep(0.01)
        second = sessions / "session-log-2026-06-06-second.md"
        second.write_text(
            _session_log(
                "Second",
                "We decided to use Postgres for storage.\nFixed the migration.",
            ),
            encoding="utf-8",
        )

        daemon = ConsolidationDaemon(vault, use_llm=False)
        note = daemon.run_once()
        assert note is not None

        # The consolidated note was written and is valid.
        out = vault / "wiki" / "consolidated" / f"{note.date}.md"
        assert out.exists()
        rendered = out.read_text(encoding="utf-8")
        assert validate_text(rendered).ok
        assert "type: consolidated" in rendered

        # Two sessions merged, contradiction resolved most-recent-wins.
        assert len(note.sessions_processed) == 2
        assert len(note.contradictions) == 1
        assert any("Postgres" in d for d in note.decisions)
        assert not any("SQLite" in d for d in note.decisions)

        # Watermark advanced; a second pass finds nothing new.
        assert daemon.read_last_consolidation() is not None
        assert daemon.run_once() is None

    def test_concurrent_run_is_skipped(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        (vault / "sessions" / "session-log-2026-06-05-a.md").write_text(
            _session_log("A", "Created a.py."), encoding="utf-8"
        )
        daemon = ConsolidationDaemon(vault, use_llm=False)
        # Hold the consolidation lock so run_once cannot acquire it.
        from eidetic_os.filelock import acquire_lock, release_lock

        target = daemon._lock_target  # noqa: SLF001 - testing the lock guard
        target.parent.mkdir(parents=True, exist_ok=True)
        acquire_lock(target)
        try:
            assert daemon.run_once() is None
        finally:
            release_lock(target)


# ── status helper ───────────────────────────────────────────────────────────────


class TestStatus:
    def test_status_reports_pending(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        (vault / "sessions" / "session-log-2026-06-05-a.md").write_text(
            _session_log("A", "Created a.py."), encoding="utf-8"
        )
        info = sleeptime.consolidation_status(vault)
        assert info["vault_exists"] is True
        assert info["sessions_pending"] == 1
        assert info["last_consolidation"] is None
        assert info["consolidated_notes"] == 0
        assert info["facts_integration"] in (True, False)

    def test_status_missing_vault(self, tmp_path: Path) -> None:
        info = sleeptime.consolidation_status(tmp_path / "absent")
        assert info["vault_exists"] is False
        assert info["sessions_pending"] == 0


# ── daemon lifecycle ────────────────────────────────────────────────────────────


class TestFactsIntegration:
    def test_facts_for_returns_strings_or_empty(self) -> None:
        # Whether or not facts.py is merged, facts_for must return a list of str.
        result = sleeptime.facts_for("We decided to use SQLite for storage.")
        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_facts_do_not_pollute_decisions(self, tmp_path: Path) -> None:
        # Heuristic decisions stay clean (clause form) regardless of facts.py;
        # any facts are routed to the separate facts field.
        vault = _make_vault(tmp_path)
        (vault / "sessions" / "session-log-2026-06-05-a.md").write_text(
            _session_log("A", "We decided to use Typer for the CLI."),
            encoding="utf-8",
        )
        daemon = ConsolidationDaemon(vault, use_llm=False)
        note = daemon.run_once()
        assert note is not None
        # No ExtractedFact repr or raw object leaked into decisions.
        assert all("ExtractedFact" not in d for d in note.decisions)
        assert any("Typer" in d for d in note.decisions)

    def test_extract_session_attaches_facts_when_available(
        self, tmp_path: Path
    ) -> None:
        if not sleeptime.FACTS_AVAILABLE:
            pytest.skip("facts.py (#22) not merged yet")
        vault = _make_vault(tmp_path)
        log = vault / "sessions" / "session-log-2026-06-05-a.md"
        log.write_text(
            _session_log("A", "We decided to use Postgres for storage."),
            encoding="utf-8",
        )
        daemon = ConsolidationDaemon(vault, use_llm=False)
        takeaways = daemon.extract_session(log)
        assert isinstance(takeaways.facts, list)
        # render still validates with a facts section present.
        note = merge_takeaways([takeaways], date="2026-06-06")
        assert validate_text(render_note(note)).ok


class TestDaemonLifecycle:
    def test_start_and_stop(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        # Long interval so the loop runs once then waits; stop() interrupts it.
        daemon = ConsolidationDaemon(vault, interval_hours=24.0, use_llm=False)
        daemon.start()
        assert daemon.is_running
        daemon.stop(timeout=5.0)
        assert not daemon.is_running

    def test_stop_is_idempotent(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        daemon = ConsolidationDaemon(vault, use_llm=False)
        daemon.stop()  # never started — no error
        daemon.start()
        daemon.stop()
        daemon.stop()  # double stop — no error
