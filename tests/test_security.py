"""Tests for the skill security layer: AST scanner, runtime sandbox, install gate.

The scanner tests feed it known-dangerous and known-safe source and assert the
severities. The sandbox tests exercise timeout and (where the platform enforces
it) the memory cap. The integration tests drive ``eidetic skills install`` against
a temp skill tree and assert that BLOCK findings refuse the install while WARN
findings need ``--force``.

All tests are hermetic — they write skills into ``tmp_path`` and point the
install root and audit log at temp dirs, never touching the real vault.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eidetic_os import sandbox, security
from eidetic_os.cli import app
from eidetic_os.security import Severity

runner = CliRunner()


# ── helpers ───────────────────────────────────────────────────────────────────
def _write(path: Path, source: str) -> Path:
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return path


def _codes(report: security.SecurityReport, severity: Severity) -> set[str]:
    return {f.code for f in report.with_severity(severity)}


# ══════════════════════════════════════════════════════════════════════════════
# AST scanner — BLOCK level
# ══════════════════════════════════════════════════════════════════════════════
def test_scan_flags_os_system_as_block(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "import os\nos.system('rm -rf /')\n")
    report = security.scan_skill(tmp_path)
    assert "os-system" in _codes(report, Severity.BLOCK)
    assert not security.is_safe(report)


def test_scan_flags_subprocess_shell_true_as_block(tmp_path: Path) -> None:
    _write(
        tmp_path / "s.py",
        "import subprocess\nsubprocess.run('ls -la', shell=True)\n",
    )
    report = security.scan_skill(tmp_path)
    assert "subprocess-shell" in _codes(report, Severity.BLOCK)


def test_scan_flags_eval_and_exec_as_block(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "eval('2+2')\nexec('x=1')\n")
    report = security.scan_skill(tmp_path)
    blocks = _codes(report, Severity.BLOCK)
    assert {"eval-call", "exec-call"} <= blocks


def test_scan_flags_dynamic_import_as_block(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "mod = __import__('os')\n")
    report = security.scan_skill(tmp_path)
    assert "dynamic-import" in _codes(report, Severity.BLOCK)


def test_scan_resolves_from_import_alias_for_subprocess(tmp_path: Path) -> None:
    # `from subprocess import run` must still be recognised as subprocess.run.
    _write(tmp_path / "s.py", "from subprocess import run\nrun('x', shell=True)\n")
    report = security.scan_skill(tmp_path)
    assert "subprocess-shell" in _codes(report, Severity.BLOCK)


def test_scan_resolves_module_alias_for_os_system(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "import os as operating\noperating.system('whoami')\n")
    report = security.scan_skill(tmp_path)
    assert "os-system" in _codes(report, Severity.BLOCK)


def test_scan_reports_syntax_error_as_block(tmp_path: Path) -> None:
    _write(tmp_path / "broken.py", "def oops(:\n")
    report = security.scan_skill(tmp_path)
    assert "syntax-error" in _codes(report, Severity.BLOCK)
    assert not security.is_safe(report)


# ══════════════════════════════════════════════════════════════════════════════
# AST scanner — WARN / INFO levels
# ══════════════════════════════════════════════════════════════════════════════
def test_scan_flags_env_access_as_warn(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "import os\nkey = os.environ['SECRET']\n")
    report = security.scan_skill(tmp_path)
    assert "env-access" in _codes(report, Severity.WARN)


def test_scan_flags_socket_import_as_warn(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "import socket\n")
    report = security.scan_skill(tmp_path)
    assert "socket-import" in _codes(report, Severity.WARN)


def test_scan_flags_open_write_mode_as_warn(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "open('out.txt', 'w')\n")
    report = security.scan_skill(tmp_path)
    assert "open-write" in _codes(report, Severity.WARN)


def test_scan_open_read_mode_is_not_flagged(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "open('in.txt', 'r')\nopen('also.txt')\n")
    report = security.scan_skill(tmp_path)
    assert "open-write" not in _codes(report, Severity.WARN)


def test_scan_subprocess_without_shell_is_warn_not_block(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "import subprocess\nsubprocess.run(['ls', '-la'])\n")
    report = security.scan_skill(tmp_path)
    assert "subprocess-exec" in _codes(report, Severity.WARN)
    assert "subprocess-shell" not in _codes(report, Severity.BLOCK)
    assert security.is_safe(report)  # WARN alone is still installable


def test_scan_flags_requests_import_as_info(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "import requests\n")
    report = security.scan_skill(tmp_path)
    assert "requests-import" in _codes(report, Severity.INFO)


# ══════════════════════════════════════════════════════════════════════════════
# AST scanner — known-safe code and report shape
# ══════════════════════════════════════════════════════════════════════════════
def test_scan_known_safe_skill_has_no_findings(tmp_path: Path) -> None:
    _write(
        tmp_path / "safe.py",
        """
        import json


        def greet(name: str) -> str:
            return json.dumps({"hello": name})
        """,
    )
    report = security.scan_skill(tmp_path)
    assert report.findings == ()
    assert security.is_safe(report)
    assert report.counts == {"BLOCK": 0, "WARN": 0, "INFO": 0}


def test_scan_skips_non_python_files(tmp_path: Path) -> None:
    _write(tmp_path / "SKILL.md", "os.system('not python')\n")
    _write(tmp_path / "notes.txt", "eval('also not scanned')\n")
    report = security.scan_skill(tmp_path)
    assert report.scanned_files == ()
    assert report.findings == ()


def test_scan_recurses_into_subdirectories(tmp_path: Path) -> None:
    nested = tmp_path / "lib"
    nested.mkdir()
    _write(nested / "deep.py", "import os\nos.system('x')\n")
    report = security.scan_skill(tmp_path)
    assert "os-system" in _codes(report, Severity.BLOCK)
    assert len(report.scanned_files) == 1


def test_scan_single_file_path(tmp_path: Path) -> None:
    target = _write(tmp_path / "one.py", "eval('1')\n")
    report = security.scan_skill(target)
    assert "eval-call" in _codes(report, Severity.BLOCK)


def test_findings_sorted_most_severe_first(tmp_path: Path) -> None:
    _write(
        tmp_path / "mixed.py",
        "import requests\nimport socket\nimport os\nos.system('x')\n",
    )
    report = security.scan_skill(tmp_path)
    ranks = [f.severity.rank for f in report.findings]
    assert ranks == sorted(ranks, reverse=True)


def test_finding_location_is_relative(tmp_path: Path) -> None:
    _write(tmp_path / "s.py", "eval('1')\n")
    report = security.scan_skill(tmp_path)
    loc = report.blocks[0].location(relative_to=tmp_path)
    assert loc == "s.py:1:0"


# ══════════════════════════════════════════════════════════════════════════════
# Runtime sandbox
# ══════════════════════════════════════════════════════════════════════════════
def test_sandbox_runs_clean_script(tmp_path: Path) -> None:
    script = _write(tmp_path / "ok.py", "print('hello from sandbox')\n")
    result = sandbox.run_sandboxed(script, timeout=10)
    assert result.ok
    assert result.exit_code == 0
    assert "hello from sandbox" in result.stdout
    assert not result.timed_out


def test_sandbox_captures_nonzero_exit(tmp_path: Path) -> None:
    script = _write(tmp_path / "fail.py", "import sys\nsys.exit(3)\n")
    result = sandbox.run_sandboxed(script, timeout=10)
    assert result.exit_code == 3
    assert not result.ok


def test_sandbox_enforces_timeout(tmp_path: Path) -> None:
    script = _write(tmp_path / "slow.py", "import time\nwhile True:\n    time.sleep(0.05)\n")
    result = sandbox.run_sandboxed(script, timeout=1)
    assert result.timed_out
    assert not result.ok
    # Killed near the deadline, not left to run forever.
    assert result.duration_seconds < 5


def test_sandbox_missing_script_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sandbox.run_sandboxed(tmp_path / "nope.py")


def test_sandbox_env_excludes_parent_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EIDETIC_SECRET_TOKEN", "super-secret")
    script = _write(
        tmp_path / "leak.py",
        "import os\nprint('LEAK' if 'EIDETIC_SECRET_TOKEN' in os.environ else 'CLEAN')\n",
    )
    result = sandbox.run_sandboxed(script, timeout=10)
    assert "CLEAN" in result.stdout
    assert "LEAK" not in result.stdout


def test_sandbox_env_denies_network_proxy_by_default() -> None:
    denied = sandbox.build_sandbox_env(allow_network=False)
    assert denied["HTTPS_PROXY"] == sandbox._DEAD_PROXY
    allowed = sandbox.build_sandbox_env(allow_network=True)
    assert "HTTPS_PROXY" not in allowed


def _memory_limit_enforced() -> bool:
    """Probe whether this platform actually honours the address-space rlimit.

    macOS silently ignores ``RLIMIT_AS``; Linux enforces it. We allocate well
    past a generous cap and see whether the child is killed.
    """
    if sys.platform.startswith("win"):
        return False
    import tempfile

    probe_dir = Path(tempfile.mkdtemp())
    probe = probe_dir / "probe.py"
    probe.write_text("x = bytearray(2 * 1024 * 1024 * 1024)\nprint(len(x))\n")
    result = sandbox.run_sandboxed(probe, timeout=15, memory_mb=256)
    return not result.ok


def test_sandbox_enforces_memory_limit(tmp_path: Path) -> None:
    if not _memory_limit_enforced():
        pytest.skip("platform does not enforce RLIMIT_AS (e.g. macOS)")
    script = _write(
        tmp_path / "hog.py",
        "x = bytearray(2 * 1024 * 1024 * 1024)\nprint(len(x))\n",
    )
    result = sandbox.run_sandboxed(script, timeout=15, memory_mb=256)
    assert not result.ok  # MemoryError → non-zero exit


# ══════════════════════════════════════════════════════════════════════════════
# Install integration — scan gates `eidetic skills install`
# ══════════════════════════════════════════════════════════════════════════════
def _make_skill(skills_root: Path, slug: str, *, py_source: str) -> Path:
    """Create a minimal installable skill with a SKILL.md and one .py file."""
    skill_dir = skills_root / slug
    skill_dir.mkdir(parents=True)
    _write(
        skill_dir / "SKILL.md",
        f"""
        ---
        name: {slug}
        description: A test skill.
        ---

        # {slug}
        """,
    )
    _write(skill_dir / "code.py", py_source)
    return skill_dir


@pytest.fixture
def install_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Point the skill source dir and install root at temp locations.

    Returns ``(skills_source_dir, install_root)``. ``_skills.skills_dir`` is
    monkeypatched so ``install_skill`` reads our crafted skills instead of the
    repo's, and the audit log is redirected so ``security report`` is hermetic.
    """
    from eidetic_os import _skills

    source = tmp_path / "src"
    source.mkdir()
    install_root = tmp_path / "installed"
    monkeypatch.setattr(_skills, "skills_dir", lambda: source)
    monkeypatch.setenv("EIDETIC_SKILLS_DIR", str(install_root))
    monkeypatch.setenv("EIDETIC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    return source, install_root


def test_install_refuses_blocked_skill(install_env: tuple[Path, Path]) -> None:
    source, install_root = install_env
    _make_skill(source, "evil", py_source="import os\nos.system('rm -rf /')\n")

    result = runner.invoke(app, ["skills", "install", "evil"])

    assert result.exit_code == 1
    assert "BLOCK" in result.output or "block" in result.output.lower()
    assert not (install_root / "evil" / "SKILL.md").exists()


def test_install_block_not_overridable_by_force(
    install_env: tuple[Path, Path],
) -> None:
    source, install_root = install_env
    _make_skill(source, "evil", py_source="eval('2+2')\n")

    result = runner.invoke(app, ["skills", "install", "evil", "--force"])

    assert result.exit_code == 1
    assert not (install_root / "evil" / "SKILL.md").exists()


def test_install_warns_then_requires_force(install_env: tuple[Path, Path]) -> None:
    source, install_root = install_env
    _make_skill(source, "netty", py_source="import socket\n")

    # Without --force: refused with a warning, nothing written.
    first = runner.invoke(app, ["skills", "install", "netty"])
    assert first.exit_code == 1
    assert "warning" in first.output.lower()
    assert not (install_root / "netty" / "SKILL.md").exists()

    # With --force: installed.
    second = runner.invoke(app, ["skills", "install", "netty", "--force"])
    assert second.exit_code == 0
    assert (install_root / "netty" / "SKILL.md").exists()


def test_install_clean_skill_succeeds(install_env: tuple[Path, Path]) -> None:
    source, install_root = install_env
    _make_skill(source, "tidy", py_source="import json\nprint(json.dumps({}))\n")

    result = runner.invoke(app, ["skills", "install", "tidy"])

    assert result.exit_code == 0, result.output
    assert (install_root / "tidy" / "SKILL.md").exists()


def test_install_attempts_recorded_in_audit(install_env: tuple[Path, Path]) -> None:
    from eidetic_os import audit

    source, _ = install_env
    _make_skill(source, "evil", py_source="os.system('x')\n")  # scanned, never run
    _make_skill(source, "tidy", py_source="x = 1\n")

    runner.invoke(app, ["skills", "install", "evil"])
    runner.invoke(app, ["skills", "install", "tidy"])

    entries = audit.read_audit(action="skill_install", limit=-1)
    statuses = [e.get("status") for e in entries]
    assert "error" in statuses  # the blocked install
    assert "success" in statuses  # the clean install


# ══════════════════════════════════════════════════════════════════════════════
# CLI — `eidetic security scan` / `eidetic security report`
# ══════════════════════════════════════════════════════════════════════════════
def test_security_scan_command_exits_nonzero_on_block(tmp_path: Path) -> None:
    _make_skill(tmp_path, "evil", py_source="import os\nos.system('x')\n")
    result = runner.invoke(app, ["security", "scan", str(tmp_path / "evil")])
    assert result.exit_code == 1
    assert "BLOCK" in result.output


def test_security_scan_command_clean_exits_zero(tmp_path: Path) -> None:
    _make_skill(tmp_path, "tidy", py_source="x = 1\n")
    result = runner.invoke(app, ["security", "scan", str(tmp_path / "tidy")])
    assert result.exit_code == 0


def test_security_report_summarises_attempts(
    install_env: tuple[Path, Path],
) -> None:
    source, _ = install_env
    _make_skill(source, "evil", py_source="eval('1')\n")
    _make_skill(source, "tidy", py_source="x = 1\n")
    runner.invoke(app, ["skills", "install", "evil"])
    runner.invoke(app, ["skills", "install", "tidy"])

    result = runner.invoke(app, ["security", "report"])
    assert result.exit_code == 0
    assert "installed:" in result.output
    assert "blocked:" in result.output
