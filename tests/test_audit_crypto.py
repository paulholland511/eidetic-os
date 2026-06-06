"""Tests for Ed25519 audit signing & the hash chain (``eidetic_os.audit_crypto``).

Fully hermetic: every test points ``EIDETIC_AUDIT_PATH`` (and therefore the key
path, which is derived from it) at a temp directory, so nothing touches the real
vault or a persistent key.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eidetic_os import audit, audit_crypto
from eidetic_os.audit_crypto import AuditSigner, VerificationResult, entry_hash
from eidetic_os.cli import app

runner = CliRunner()


@pytest.fixture()
def audit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the audit trail (and signing key) into a temp dir."""
    path = tmp_path / ".eidetic" / "audit.jsonl"
    monkeypatch.setenv("EIDETIC_AUDIT_PATH", str(path))
    monkeypatch.delenv("EIDETIC_AUDIT_KEY", raising=False)
    audit_crypto.reset_default_signer()
    return path


def _entry(action: str = "embed") -> dict[str, object]:
    return {
        "timestamp": "2026-06-06T12:00:00+00:00",
        "action": action,
        "trigger": "cli",
        "status": "success",
        "duration_seconds": 1.0,
        "changes": ["3 new"],
        "context": "eidetic embed",
        "error": None,
    }


# ── Keypair generation ────────────────────────────────────────────────────────
def test_keygen_creates_private_and_public_files(tmp_path: Path) -> None:
    key_path = tmp_path / "audit_key"
    signer = AuditSigner(key_path)

    assert key_path.exists()
    assert key_path.with_suffix(".pub").exists()
    assert signer.available
    # Private key is owner-only.
    assert (key_path.stat().st_mode & 0o077) == 0
    # Private is PEM/PKCS8, public is PEM SubjectPublicKeyInfo.
    assert key_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    assert key_path.with_suffix(".pub").read_bytes().startswith(b"-----BEGIN PUBLIC KEY-----")


def test_existing_key_is_loaded_not_regenerated(tmp_path: Path) -> None:
    key_path = tmp_path / "audit_key"
    first = AuditSigner(key_path)
    original = key_path.read_bytes()

    second = AuditSigner(key_path)
    assert key_path.read_bytes() == original  # not overwritten
    # Same key → same embedded public key.
    assert first.sign_entry(_entry())["public_key"] == second.sign_entry(_entry())["public_key"]


# ── Sign / verify round-trip ──────────────────────────────────────────────────
def test_sign_adds_expected_fields(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    signed = signer.sign_entry(_entry())

    for field in ("signature", "public_key", "signed_at", "prev_hash"):
        assert field in signed
    # Signature and public key are valid base64.
    base64.b64decode(signed["signature"])
    assert len(base64.b64decode(signed["public_key"])) == 32  # raw Ed25519 public key
    # Original fields are preserved untouched.
    assert signed["action"] == "embed"
    assert signed["changes"] == ["3 new"]


def test_sign_verify_roundtrip(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    signed = signer.sign_entry(_entry())
    assert signer.verify_entry(signed) is True


def test_verify_fails_for_unsigned_entry(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    assert signer.verify_entry(_entry()) is False


def test_first_entry_has_null_prev_hash(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    signed = signer.sign_entry(_entry())
    assert signed["prev_hash"] is None


# ── Tamper detection ──────────────────────────────────────────────────────────
def test_tampering_with_content_breaks_verification(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    signed = signer.sign_entry(_entry())

    signed["action"] = "rm -rf"  # attacker edits the recorded action
    assert signer.verify_entry(signed) is False


def test_tampering_with_changes_breaks_verification(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    signed = signer.sign_entry(_entry())

    signed["changes"] = ["nothing happened"]
    assert signer.verify_entry(signed) is False


def test_swapped_signature_fails(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    a = signer.sign_entry(_entry("embed"))
    b = signer.sign_entry(_entry("commit"))

    a["signature"] = b["signature"]  # graft another entry's signature
    assert signer.verify_entry(a) is False


# ── Hash chain integrity ──────────────────────────────────────────────────────
def _write_trail(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
        encoding="utf-8",
    )


def test_chain_links_each_entry_to_the_previous(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    first = signer.sign_entry(_entry("a"))
    second = signer.sign_entry(_entry("b"))
    third = signer.sign_entry(_entry("c"))

    assert first["prev_hash"] is None
    assert second["prev_hash"] == entry_hash(first)
    assert third["prev_hash"] == entry_hash(second)


def test_verify_trail_all_valid(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    _write_trail(trail, [signer.sign_entry(_entry(a)) for a in ("a", "b", "c")])

    result = signer.verify_trail(trail)
    assert isinstance(result, VerificationResult)
    assert result.total_entries == 3
    assert result.verified == 3
    assert result.unsigned == 0
    assert result.tampered == 0
    assert result.chain_intact is True
    assert result.ok is True
    assert result.first_tampered_line is None


def test_verify_trail_detects_tampered_entry(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    entries = [signer.sign_entry(_entry(a)) for a in ("a", "b", "c")]
    entries[1]["status"] = "error"  # tamper with the 2nd line's content
    _write_trail(trail, entries)

    result = signer.verify_trail(trail)
    assert result.tampered >= 1
    assert result.first_tampered_line == 2
    assert result.chain_intact is False
    assert result.ok is False


def test_verify_trail_detects_reordering(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    entries = [signer.sign_entry(_entry(a)) for a in ("a", "b", "c")]
    entries[1], entries[2] = entries[2], entries[1]  # swap order → chain breaks
    _write_trail(trail, entries)

    result = signer.verify_trail(trail)
    assert result.chain_intact is False
    assert result.tampered >= 1


def test_verify_trail_detects_deletion(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    entries = [signer.sign_entry(_entry(a)) for a in ("a", "b", "c")]
    del entries[1]  # drop the middle entry → c's prev_hash no longer matches
    _write_trail(trail, entries)

    result = signer.verify_trail(trail)
    assert result.chain_intact is False
    assert result.tampered >= 1


def test_verify_trail_counts_unsigned(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    _write_trail(trail, [signer.sign_entry(_entry("a")), _entry("b")])

    result = signer.verify_trail(trail)
    assert result.unsigned == 1
    assert result.chain_intact is False


# ── Retroactive signing ───────────────────────────────────────────────────────
def test_sign_trail_signs_unsigned_entries(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    _write_trail(trail, [_entry("a"), _entry("b"), _entry("c")])

    signed_count = signer.sign_trail(trail)
    assert signed_count == 3

    result = AuditSigner(tmp_path / "audit_key").verify_trail(trail)
    assert result.ok is True
    assert result.verified == 3


def test_sign_trail_is_idempotent(tmp_path: Path) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    trail = tmp_path / "audit.jsonl"
    _write_trail(trail, [_entry("a"), _entry("b")])

    assert signer.sign_trail(trail) == 2
    # Re-signing an already-signed, intact trail changes nothing.
    assert signer.sign_trail(trail) == 0


# ── Live append path (audit.log_action integration) ───────────────────────────
def test_log_action_signs_new_entries(audit_env: Path) -> None:
    audit.log_action("embed", "cli", "success", changes=["3 new"])
    audit.log_action("commit", "scheduled", "success")

    entries = [json.loads(line) for line in audit_env.read_text().splitlines()]
    assert len(entries) == 2
    signer = AuditSigner()
    assert all(signer.verify_entry(e) for e in entries)
    # The second entry chains onto the first.
    assert entries[0]["prev_hash"] is None
    assert entries[1]["prev_hash"] == entry_hash(entries[0])


def test_log_action_trail_verifies_via_signer(audit_env: Path) -> None:
    for i in range(4):
        audit.log_action(f"action{i}", "manual", "success")
    result = AuditSigner().verify_trail(audit_env)
    assert result.total_entries == 4
    assert result.ok is True


# ── Graceful fallback without cryptography ────────────────────────────────────
def test_sign_entry_noop_without_cryptography(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_crypto, "CRYPTO_AVAILABLE", False)
    monkeypatch.setattr(audit_crypto, "_warned_missing", False)
    signer = AuditSigner(tmp_path / "audit_key")

    assert signer.available is False
    entry = _entry()
    out = signer.sign_entry(entry)
    assert out == entry  # unchanged, unsigned
    assert "signature" not in out


def test_log_action_writes_unsigned_without_cryptography(
    audit_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_crypto, "CRYPTO_AVAILABLE", False)
    monkeypatch.setattr(audit_crypto, "_warned_missing", False)
    audit_crypto.reset_default_signer()

    written = audit.log_action("embed", "cli", "success")
    assert "signature" not in written
    entry = json.loads(audit_env.read_text().splitlines()[0])
    assert "signature" not in entry  # written, just unsigned


def test_verify_entry_false_without_cryptography(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signer = AuditSigner(tmp_path / "audit_key")
    signed = signer.sign_entry(_entry())
    monkeypatch.setattr(audit_crypto, "CRYPTO_AVAILABLE", False)
    assert signer.verify_entry(signed) is False


# ── CLI commands ──────────────────────────────────────────────────────────────
def test_cli_keygen_then_verify(audit_env: Path) -> None:
    result = runner.invoke(app, ["audit", "keygen"])
    assert result.exit_code == 0, result.output
    assert audit_crypto.default_key_path().exists()


def test_cli_sign_and_verify(audit_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Disable auto-signing so we can exercise retroactive `audit sign`.
    monkeypatch.setattr(audit_crypto, "CRYPTO_AVAILABLE", False)
    audit_crypto.reset_default_signer()
    audit.log_action("embed", "cli", "success")
    audit.log_action("commit", "cli", "success")

    monkeypatch.setattr(audit_crypto, "CRYPTO_AVAILABLE", True)
    audit_crypto.reset_default_signer()

    sign_result = runner.invoke(app, ["audit", "sign"])
    assert sign_result.exit_code == 0, sign_result.output
    assert "signed 2" in sign_result.output

    verify_result = runner.invoke(app, ["audit", "verify"])
    assert verify_result.exit_code == 0, verify_result.output
    assert "fully verified" in verify_result.output


def test_cli_verify_detects_tampering(audit_env: Path) -> None:
    runner.invoke(app, ["audit", "keygen"])
    audit.log_action("embed", "cli", "success")
    audit.log_action("commit", "cli", "success")

    # Tamper with the first line on disk.
    lines = audit_env.read_text().splitlines()
    first = json.loads(lines[0])
    first["action"] = "exfiltrate"
    lines[0] = json.dumps(first)
    audit_env.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = runner.invoke(app, ["audit", "verify"])
    assert result.exit_code == 1
    assert "FAILED" in result.output


def test_cli_export_json_includes_signature(audit_env: Path) -> None:
    audit.log_action("embed", "cli", "success")
    result = runner.invoke(app, ["audit", "export", "--format", "json"])
    assert result.exit_code == 0, result.output
    exported = json.loads(result.output)
    assert exported[0].get("signature")
    assert exported[0].get("public_key")
