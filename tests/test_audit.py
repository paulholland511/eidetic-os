"""Tests for the append-only audit trail (``eidetic_os.audit``) and `eidetic audit`.

These are fully hermetic: every test points ``EIDETIC_AUDIT_PATH`` at a temp file
via the ``audit_path`` fixture, so nothing touches the real vault.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eidetic_os import audit
from eidetic_os.cli import app

runner = CliRunner()


@pytest.fixture()
def audit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the audit log to a temp file for the duration of a test."""
    path = tmp_path / ".eidetic" / "audit.jsonl"
    monkeypatch.setenv("EIDETIC_AUDIT_PATH", str(path))
    return path


# ── Core logger ───────────────────────────────────────────────────────────────
def test_log_action_creates_file_and_appends(audit_file: Path) -> None:
    audit.log_action("embed", "cli", "success", changes=["3 new"], context="eidetic embed")
    assert audit_file.exists()

    entries = [json.loads(line) for line in audit_file.read_text().splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "embed"
    assert entry["trigger"] == "cli"
    assert entry["status"] == "success"
    assert entry["changes"] == ["3 new"]
    assert entry["context"] == "eidetic embed"
    assert entry["error"] is None
    # Timestamp is ISO 8601 and parseable.
    assert datetime.fromisoformat(entry["timestamp"]).tzinfo is not None


def test_log_action_appends_multiple(audit_file: Path) -> None:
    for i in range(5):
        audit.log_action(f"action{i}", "manual", "success")
    assert len(audit_file.read_text().splitlines()) == 5


def test_log_action_records_duration_and_error(audit_file: Path) -> None:
    audit.log_action(
        "commit", "scheduled", "error",
        context="nightly", error="boom\ntraceback", duration=1.23456,
    )
    entry = json.loads(audit_file.read_text().splitlines()[0])
    assert entry["status"] == "error"
    assert entry["duration_seconds"] == 1.235  # rounded to 3 dp
    assert entry["error"].startswith("boom")


def test_log_action_rejects_bad_status(audit_file: Path) -> None:
    with pytest.raises(ValueError):
        audit.log_action("x", "cli", "bogus")


# ── Reading & filtering ───────────────────────────────────────────────────────
def test_read_audit_returns_chronological(audit_file: Path) -> None:
    audit.log_action("first", "cli", "success")
    audit.log_action("second", "cli", "success")
    entries = audit.read_audit()
    assert [e["action"] for e in entries] == ["first", "second"]


def test_read_audit_filters_by_action(audit_file: Path) -> None:
    audit.log_action("embed", "cli", "success")
    audit.log_action("commit", "cli", "success")
    audit.log_action("embed", "cli", "error")
    entries = audit.read_audit(action="embed")
    assert len(entries) == 2
    assert all(e["action"] == "embed" for e in entries)


def test_read_audit_limit_returns_most_recent(audit_file: Path) -> None:
    for i in range(10):
        audit.log_action(f"a{i}", "cli", "success")
    entries = audit.read_audit(limit=3)
    assert [e["action"] for e in entries] == ["a7", "a8", "a9"]


def test_read_audit_since_relative(audit_file: Path) -> None:
    # Hand-write one old and one new entry so timestamps are deterministic.
    old = {
        "timestamp": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "action": "old", "trigger": "cli", "status": "success",
        "duration_seconds": None, "changes": [], "context": "", "error": None,
    }
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.write_text(json.dumps(old) + "\n")
    audit.log_action("new", "cli", "success")

    recent = audit.read_audit(since="2d")
    assert [e["action"] for e in recent] == ["new"]


def test_read_audit_since_iso_date(audit_file: Path) -> None:
    audit.log_action("now", "cli", "success")
    assert audit.read_audit(since="2000-01-01")  # everything is after this
    assert not audit.read_audit(since="2999-01-01")  # nothing after this


def test_read_audit_skips_malformed_lines(audit_file: Path) -> None:
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.write_text('not json\n{"action": "ok", "status": "success", '
                          '"timestamp": "2026-06-01T00:00:00+00:00"}\n\n')
    entries = audit.read_audit()
    assert len(entries) == 1
    assert entries[0]["action"] == "ok"


def test_read_audit_empty_when_no_file(audit_file: Path) -> None:
    assert audit.read_audit() == []


# ── Rotation ──────────────────────────────────────────────────────────────────
def test_rotation_when_exceeding_max(audit_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Shrink the cap so a couple of entries trigger rotation.
    monkeypatch.setattr(audit, "MAX_BYTES", 200)
    for i in range(20):
        audit.log_action(f"action-with-a-longish-name-{i}", "cli", "success")

    rotated = audit_file.with_suffix(audit_file.suffix + ".1")
    assert rotated.exists(), "expected at least one rotated backup"
    # read_audit spans the active file and backups → all 20 entries recoverable.
    actions = [e["action"] for e in audit.read_audit(limit=-1)]
    assert len(actions) == 20
    assert actions[0] == "action-with-a-longish-name-0"  # oldest first
    assert actions[-1] == "action-with-a-longish-name-19"


def test_rotation_shifts_existing_backups(audit_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "MAX_BYTES", 150)
    for i in range(30):
        audit.log_action(f"entry-{i}", "cli", "success")
    # Multiple numbered backups should now exist.
    backups = sorted(audit_file.parent.glob(audit_file.name + ".*"))
    assert len(backups) >= 2


# ── CLI: audit show / tail / export ───────────────────────────────────────────
def _seed(n: int = 3) -> None:
    audit.log_action("embed", "cli", "success", changes=["2 new"], context="eidetic embed")
    audit.log_action("commit", "scheduled", "success", changes=["commit abc123"])
    audit.log_action("email", "manual", "error", error="smtp refused", context="eidetic email")


def test_cli_audit_show(audit_file: Path) -> None:
    _seed()
    result = runner.invoke(app, ["audit", "show"])
    assert result.exit_code == 0
    assert "embed" in result.stdout
    assert "commit" in result.stdout
    assert "smtp refused" in result.stdout  # error detail line


def test_cli_audit_show_filter_action(audit_file: Path) -> None:
    _seed()
    result = runner.invoke(app, ["audit", "show", "--action", "embed"])
    assert result.exit_code == 0
    assert "embed" in result.stdout
    assert "commit" not in result.stdout


def test_cli_audit_show_empty(audit_file: Path) -> None:
    result = runner.invoke(app, ["audit", "show"])
    assert result.exit_code == 0
    assert "No audit entries" in result.stdout


def test_cli_audit_show_bad_since(audit_file: Path) -> None:
    result = runner.invoke(app, ["audit", "show", "--since", "not-a-date"])
    assert result.exit_code == 2


def test_cli_audit_tail(audit_file: Path) -> None:
    _seed()
    result = runner.invoke(app, ["audit", "tail"])
    assert result.exit_code == 0
    assert "email" in result.stdout


def test_cli_audit_export_csv(audit_file: Path) -> None:
    _seed()
    result = runner.invoke(app, ["audit", "export", "--format", "csv"])
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert lines[0].startswith("timestamp,action,trigger,status")
    assert any("embed" in line for line in lines[1:])


def test_cli_audit_export_json_to_file(audit_file: Path, tmp_path: Path) -> None:
    _seed()
    out = tmp_path / "report.json"
    result = runner.invoke(app, ["audit", "export", "--format", "json", "--output", str(out)])
    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert len(data) == 3


def test_cli_audit_export_bad_format(audit_file: Path) -> None:
    result = runner.invoke(app, ["audit", "export", "--format", "xml"])
    assert result.exit_code == 2
