"""Smoke tests for the unified ``eidetic`` CLI.

These are hermetic — they exercise the Typer app in-process via ``CliRunner``
and never shell out to the underlying scripts or touch the network.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eidetic_os import __version__, cli
from eidetic_os._probe import Endpoint
from eidetic_os.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.parametrize(
    "command",
    [
        "init",
        "doctor",
        "skills",
        "embed",
        "graph",
        "commit",
        "changelog",
        "health",
        "trading",
        "email",
        "schemas",
        "session",
    ],
)
def test_command_is_registered(command: str) -> None:
    """Every documented subcommand exists and renders its help."""
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0


def test_vault_command_requires_vault_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vault-dependent commands fail fast (exit 2) when VAULT_PATH is unset."""
    monkeypatch.delenv("VAULT_PATH", raising=False)
    result = runner.invoke(app, ["trading", "--dry-run"])
    assert result.exit_code == 2
    assert "VAULT_PATH" in result.stdout


def test_email_requires_smtp_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """`eidetic email` refuses to run without SMTP credentials."""
    monkeypatch.delenv("SENDER_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)
    result = runner.invoke(app, ["email", "--subject", "hi", "--body", "x", "--to", "a@b.c"])
    assert result.exit_code == 2
    assert "SENDER_EMAIL" in result.stdout or "SMTP_APP_PASSWORD" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# init wizard
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def _no_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make backend probing return nothing — keeps the wizard off the network."""
    monkeypatch.setattr(cli, "detect_endpoints", lambda *a, **k: [])


@pytest.fixture
def _wizard_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect the wizard's .env target into a temp dir, never the real repo.

    ``init`` writes .env to ``repo_root() or cwd``. We force ``repo_root`` to
    ``None`` and chdir into ``tmp_path`` so the generated .env (and any
    side-effect) lands in the sandbox, not the developer's checkout. ``init``
    also calls ``os.environ.update`` to feed its doctor run, which bypasses
    monkeypatch's tracking — so we snapshot and restore the environment here.
    """
    monkeypatch.setattr(cli, "repo_root", lambda: None)
    monkeypatch.chdir(tmp_path)
    saved = os.environ.copy()
    try:
        yield tmp_path
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_init_yes_scaffolds_vault_and_writes_env(
    _no_backend: None, _wizard_sandbox: Path, tmp_path: Path
) -> None:
    """`eidetic init --yes` builds the vault tree, writes .env, and runs doctor."""
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", "--yes", "--vault", str(vault)])

    assert result.exit_code == 0, result.stdout
    # Vault directory tree exists.
    for sub in (".eidetic", ".rag", "wiki"):
        assert (vault / sub).is_dir(), f"missing {sub}/"
    # .env was written into the sandbox with the chosen vault path.
    env_path = _wizard_sandbox / ".env"
    assert env_path.is_file()
    assert f"VAULT_PATH={vault}" in env_path.read_text()
    # The doctor verification ran as part of init.
    assert "Verifying your setup" in result.stdout
    assert "You're ready" in result.stdout


def test_init_detects_backend_and_records_it(
    _wizard_sandbox: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A detected endpoint's host/port/embed-model are folded into the .env."""
    endpoint = Endpoint(
        label="LM Studio",
        base_url="http://localhost:5555",
        host="localhost",
        port=5555,
        models=("some-chat-model", "text-embedding-nomic-embed-text-v1.5"),
    )
    monkeypatch.setattr(cli, "detect_endpoints", lambda *a, **k: [endpoint])

    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", "--yes", "--vault", str(vault)])

    assert result.exit_code == 0, result.stdout
    env_text = (_wizard_sandbox / ".env").read_text()
    assert "EMBED_PORT=5555" in env_text
    assert "LM_STUDIO_PORT=5555" in env_text
    assert "EMBED_MODEL=text-embedding-nomic-embed-text-v1.5" in env_text
    assert "LM Studio at http://localhost:5555" in result.stdout


def test_init_does_not_overwrite_existing_env_without_force(
    _no_backend: None, _wizard_sandbox: Path, tmp_path: Path
) -> None:
    """An existing .env is preserved unless --force is given."""
    env_path = _wizard_sandbox / ".env"
    env_path.write_text("VAULT_PATH=/keep/me\n")

    result = runner.invoke(app, ["init", "--yes", "--vault", str(tmp_path / "vault")])

    assert result.exit_code == 0, result.stdout
    assert env_path.read_text() == "VAULT_PATH=/keep/me\n"
    assert "not overwriting" in result.stdout

    # With --force it is replaced.
    forced = runner.invoke(
        app, ["init", "--yes", "--force", "--vault", str(tmp_path / "vault")]
    )
    assert forced.exit_code == 0, forced.stdout
    assert "/keep/me" not in env_path.read_text()


def test_backend_env_from_endpoint_maps_fields() -> None:
    """The endpoint→.env mapping fills host/port for both embed and chat."""
    endpoint = Endpoint(
        label="Ollama",
        base_url="http://localhost:11434",
        host="localhost",
        port=11434,
        models=("llama3", "nomic-embed-text"),
    )
    values = cli._backend_env_from_endpoint(endpoint)
    assert values["EMBED_HOST"] == "localhost"
    assert values["EMBED_PORT"] == "11434"
    assert values["LM_STUDIO_PORT"] == "11434"
    assert values["EMBED_MODEL"] == "nomic-embed-text"


def test_backend_env_from_endpoint_without_embed_model() -> None:
    """No embedding model is set when the backend advertises none."""
    endpoint = Endpoint(
        label="llama.cpp",
        base_url="http://localhost:8080",
        host="localhost",
        port=8080,
        models=("chat-only-model",),
    )
    values = cli._backend_env_from_endpoint(endpoint)
    assert "EMBED_MODEL" not in values
    assert values["EMBED_PORT"] == "8080"


def test_detect_default_vault_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit VAULT_PATH always wins the smart-default contest."""
    monkeypatch.setenv("VAULT_PATH", "~/some/explicit/vault")
    assert cli._detect_default_vault().endswith("some/explicit/vault")


def test_detect_default_vault_finds_obsidian_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no env set, the first ~/Documents/Obsidian/* folder is chosen."""
    monkeypatch.delenv("VAULT_PATH", raising=False)
    home = tmp_path / "home"
    obsidian = home / "Documents" / "Obsidian"
    (obsidian / "MyNotes").mkdir(parents=True)
    monkeypatch.setattr(cli.Path, "home", classmethod(lambda cls: home))

    assert cli._detect_default_vault() == str(obsidian / "MyNotes")


# ─────────────────────────────────────────────────────────────────────────────
# doctor — diagnostics, fixes, --fix, --json
# ─────────────────────────────────────────────────────────────────────────────
from eidetic_os.backends import Backend, BackendStatus  # noqa: E402


def _by_name(results: list[cli.Check], name: str) -> cli.Check:
    return next(c for c in results if c.name == name)


@pytest.fixture
def _offline_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every network-touching part of the doctor so checks stay hermetic."""
    monkeypatch.setattr(cli.llm_backends, "forced_backend_name", lambda: None)
    monkeypatch.setattr(cli.llm_backends, "backend_statuses", lambda *a, **k: [])
    monkeypatch.setattr(cli, "_check_embeddings", lambda: ("WARN", "unreachable"))


@pytest.fixture
def _vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A vault directory wired into the environment, no git, no RAG."""
    vault = tmp_path / "vault"
    (vault / ".rag").mkdir(parents=True)
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RAG_DIR", str(vault / ".rag"))
    monkeypatch.delenv("EMBED_URL", raising=False)
    return vault


def test_doctor_groups_known_categories(_offline_llm: None, _vault: Path) -> None:
    """Every check carries one of the documented category labels."""
    results = cli._doctor_results(now=1_000_000.0)
    categories = {c.category for c in results}
    assert categories <= set(cli._DOCTOR_CATEGORIES)
    assert {"Config", "LLM", "RAG", "SMTP"} <= categories


def test_doctor_missing_vault_offers_init_fix(
    _offline_llm: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset VAULT_PATH is a FAIL that offers the (unsafe) init wizard."""
    monkeypatch.delenv("VAULT_PATH", raising=False)
    results = cli._doctor_results(now=1_000_000.0)
    vault_check = _by_name(results, "Vault path")
    assert vault_check.status == "FAIL"
    assert vault_check.fix is not None
    assert vault_check.fix.safe is False  # running init always prompts


def test_doctor_detects_stale_git_lock(_offline_llm: None, _vault: Path) -> None:
    """A stale index.lock in a git vault is a WARN with a safe auto-fix."""
    subprocess.run(["git", "init", "-q"], cwd=_vault, check=True)
    (_vault / ".git" / "index.lock").write_text("", encoding="utf-8")

    results = cli._doctor_results(now=1_000_000.0)
    lock_check = _by_name(results, "Locks")
    assert lock_check.status == "WARN"
    assert lock_check.fix is not None
    assert lock_check.fix.safe is True


def test_doctor_offers_git_init_for_non_repo_vault(
    _offline_llm: None, _vault: Path
) -> None:
    """A vault that isn't a git repo gets a WARN + unsafe git-init fix."""
    results = cli._doctor_results(now=1_000_000.0)
    repo_check = _by_name(results, "Repository")
    assert repo_check.status == "WARN"
    assert repo_check.fix is not None and repo_check.fix.safe is False


def test_doctor_stale_rag_vectors(_offline_llm: None, _vault: Path) -> None:
    """An index older than 24h warns and suggests an incremental re-embed."""
    rag = _vault / ".rag"
    (rag / "vectors.json").write_text("{}", encoding="utf-8")
    (rag / "last_embed.txt").write_text("1000000.0", encoding="utf-8")

    # 48h after the recorded embed time.
    results = cli._doctor_results(now=1_000_000.0 + 48 * 3600)
    freshness = _by_name(results, "Freshness")
    assert freshness.status == "WARN"
    assert "incremental" in (freshness.next_step or "")


def test_doctor_fresh_rag_is_ok(_offline_llm: None, _vault: Path) -> None:
    """A recently-built index passes the freshness check."""
    rag = _vault / ".rag"
    (rag / "vectors.json").write_text("{}", encoding="utf-8")
    (rag / "last_embed.txt").write_text("1000000.0", encoding="utf-8")

    results = cli._doctor_results(now=1_000_000.0 + 600)  # 10 minutes later
    assert _by_name(results, "Freshness").status == "OK"


def test_doctor_detects_icloud_offload(
    _offline_llm: None, _vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dataless (iCloud-offloaded) vectors.json raises an iCloud WARN."""
    rag = _vault / ".rag"
    (rag / "vectors.json").write_text("{}", encoding="utf-8")
    (rag / "last_embed.txt").write_text("1000000.0", encoding="utf-8")
    monkeypatch.setattr(
        cli.fileio, "is_dataless", lambda p: p.name == "vectors.json"
    )

    results = cli._doctor_results(now=1_000_000.0 + 60)
    icloud = _by_name(results, "iCloud")
    assert icloud.status == "WARN"
    assert "vectors.json" in icloud.detail


def test_doctor_diagnoses_down_forced_backend(
    _vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forced-but-down backend yields a clear diagnosis listing alternatives."""
    lmstudio = Backend("lmstudio", "LM Studio", "http://192.168.50.158:5555")
    ollama = Backend("ollama", "Ollama", "http://localhost:11434")
    monkeypatch.setattr(cli.llm_backends, "forced_backend_name", lambda: "lmstudio")
    monkeypatch.setattr(cli.llm_backends, "get_backend", lambda name: lmstudio)
    monkeypatch.setattr(
        cli.llm_backends, "probe_backend",
        lambda be, *a, **k: BackendStatus(be, False, (), "ConnectionError"),
    )
    monkeypatch.setattr(
        cli.llm_backends, "backend_statuses",
        lambda *a, **k: [BackendStatus(ollama, True, ("llama3",), None)],
    )
    monkeypatch.setattr(cli, "_check_embeddings", lambda: ("OK", "reachable"))

    backend = _by_name(cli._doctor_results(now=1_000_000.0), "Backend")
    assert backend.status == "WARN"
    assert "is not responding" in backend.detail
    assert "192.168.50.158:5555" in backend.detail
    assert "Ollama" in (backend.next_step or "")


def test_doctor_json_output(_offline_llm: None, _vault: Path) -> None:
    """`--json` emits structured checks plus a tallied summary."""
    result = runner.invoke(app, ["doctor", "--json"])
    payload = json.loads(result.stdout)
    assert "checks" in payload and "summary" in payload
    assert {"ok", "warn", "fail"} == set(payload["summary"])
    names = {c["name"] for c in payload["checks"]}
    assert "Python" in names and "Email" in names
    # The summary tallies match the rows.
    assert payload["summary"]["fail"] == sum(
        1 for c in payload["checks"] if c["status"] == "FAIL"
    )


def test_doctor_fix_clears_locks_without_prompting(
    _offline_llm: None, _vault: Path
) -> None:
    """`eidetic doctor --fix` auto-applies the safe lock-cleanup, no input needed."""
    subprocess.run(["git", "init", "-q"], cwd=_vault, check=True)
    lock = _vault / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "--fix"])  # no stdin provided

    assert not lock.exists(), result.stdout
    assert "Locks" in result.stdout
