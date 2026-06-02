"""Smoke tests for the unified ``atlas`` CLI.

These are hermetic — they exercise the Typer app in-process via ``CliRunner``
and never shell out to the underlying scripts or touch the network.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from atlas_os import __version__
from atlas_os.cli import app

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
    """`atlas email` refuses to run without SMTP credentials."""
    monkeypatch.delenv("SENDER_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)
    result = runner.invoke(app, ["email", "--subject", "hi", "--body", "x", "--to", "a@b.c"])
    assert result.exit_code == 2
    assert "SENDER_EMAIL" in result.stdout or "SMTP_APP_PASSWORD" in result.stdout
