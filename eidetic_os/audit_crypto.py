"""Cryptographic, tamper-evident signing for the Eidetic OS audit trail.

The append-only audit log (:mod:`eidetic_os.audit`) records *what* Eidetic ran on
your behalf. This module makes that record **independently verifiable**: every
entry is signed with an `Ed25519`_ key and linked to the previous entry by a
SHA-256 hash chain. Together that gives you two guarantees auditors care about:

* **Authenticity** — a valid signature proves the entry was produced by the
  holder of the private key and has not been altered since (any edit to the
  signed content invalidates the signature).
* **Completeness** — each entry embeds ``prev_hash``, the hash of the previous
  entry's signed content. Re-ordering, inserting, or deleting an entry breaks
  the chain, so you can prove the log is whole, not just that individual lines
  are genuine.

This is the kind of evidence SOC 2 (CC7 / CC8) and the EU DORA operational-
resilience regime expect from an automation system's activity log.

Entry shape
-----------
Signing augments a plain audit entry with three fields and a chain link::

    {
      ...the original audit fields (timestamp, action, status, ...),
      "prev_hash": "9f2c…",          # SHA-256 of the previous signed entry, or null
      "signature": "base64…",        # Ed25519 signature over the canonical content
      "public_key": "base64…",       # raw 32-byte Ed25519 public key (base64)
      "signed_at": "2026-06-06T…"    # when the signature was applied (UTC, ISO 8601)
    }

The signature covers the *canonical JSON* of the entry with the three signature
fields removed — i.e. every audit field **plus** ``prev_hash``. Canonical JSON
is ``json.dumps`` with sorted keys and tight separators, so the bytes are stable
across processes and Python versions.

Graceful degradation
---------------------
The ``cryptography`` package is a hard dependency of Eidetic OS, but the audit
trail must never crash the action it records. If the library is somehow missing
(a stripped install, an import error), signing becomes a no-op: entries are
written unsigned, a one-time warning is emitted, and :meth:`AuditSigner.verify_entry`
reports them as unverifiable rather than raising.

.. _Ed25519: https://ed25519.cr.yp.to/
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from eidetic_os.audit import audit_path

# ── Optional cryptography backend ─────────────────────────────────────────────
# Imported defensively so a missing/broken install degrades to "unsigned" rather
# than taking down every audited action. `CRYPTO_AVAILABLE` gates all signing.
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    CRYPTO_AVAILABLE = False


# Fields added by signing; excluded when computing the canonical bytes we sign
# and hash, so signing is idempotent and verification is reproducible.
_SIGNATURE_FIELDS = ("signature", "public_key", "signed_at")

# Emit the "cryptography missing" warning at most once per process.
_warned_missing = False


def default_key_path() -> Path:
    """Resolve the signing-key path, mirroring :func:`eidetic_os.audit.audit_path`.

    Order: ``EIDETIC_AUDIT_KEY`` → the audit trail's directory (``…/.eidetic/``)
    ``audit_key``. Resolving relative to :func:`audit_path` keeps the key beside
    the log it signs and lets tests redirect both via ``EIDETIC_AUDIT_PATH``.
    The matching public key lives at ``<key_path>.pub``.
    """
    override = os.environ.get("EIDETIC_AUDIT_KEY")
    if override:
        return Path(os.path.expanduser(override))
    return audit_path().parent / "audit_key"


def _warn_missing() -> None:
    """Warn (once) that signing is disabled because ``cryptography`` is absent."""
    global _warned_missing
    if not _warned_missing:
        print(
            "audit_crypto: 'cryptography' not installed — audit entries will be "
            "written UNSIGNED. Install it with `pip install cryptography`.",
            file=sys.stderr,
        )
        _warned_missing = True


# ── Canonicalisation & hashing ────────────────────────────────────────────────
def canonical_bytes(entry: dict[str, Any]) -> bytes:
    """Return the deterministic bytes that are signed and hashed for ``entry``.

    The signature fields are stripped first, so an entry's signed content is
    every audit field plus ``prev_hash``. Keys are sorted and separators are
    tight, giving identical bytes on every machine and Python build.
    """
    payload = {k: v for k, v in entry.items() if k not in _SIGNATURE_FIELDS}
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def entry_hash(entry: dict[str, Any]) -> str:
    """SHA-256 (hex) of an entry's canonical signed content — its chain link.

    The next entry stores this value as ``prev_hash``. Because it is computed
    over the *signed* content, tampering with an entry changes both its own
    signature and the following entry's expected ``prev_hash``.
    """
    return hashlib.sha256(canonical_bytes(entry)).hexdigest()


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying a whole audit trail.

    ``verified`` + ``unsigned`` + ``tampered`` == ``total_entries``.
    ``chain_intact`` is true only when every entry is signed, individually valid,
    and correctly linked to its predecessor by ``prev_hash``.
    """

    total_entries: int
    verified: int
    unsigned: int
    tampered: int
    first_tampered_line: Optional[int]
    chain_intact: bool

    @property
    def ok(self) -> bool:
        """True when the trail is fully signed and untampered."""
        return self.chain_intact and self.tampered == 0 and self.unsigned == 0

    def summary(self) -> str:
        """One-line human summary for CLI output and logs."""
        return (
            f"{self.total_entries} entries · {self.verified} verified · "
            f"{self.unsigned} unsigned · {self.tampered} tampered · "
            f"chain {'intact' if self.chain_intact else 'BROKEN'}"
        )


class AuditSigner:
    """Sign and verify audit entries with an Ed25519 key + SHA-256 hash chain.

    A signer loads (or generates) a keypair from ``key_path`` and ``key_path.pub``.
    It also tracks the hash of the last entry it signed so successive
    :meth:`sign_entry` calls form a chain automatically; pass ``prev_hash``
    explicitly to chain from a known point (e.g. the tail of an existing trail).
    """

    def __init__(self, key_path: str | Path | None = None) -> None:
        self.key_path = Path(key_path) if key_path is not None else default_key_path()
        self._private: Any = None
        self._public: Any = None
        self._public_b64: str | None = None
        # Hash of the most recently signed entry; seeds the next ``prev_hash``.
        self._last_hash: str | None = None
        if CRYPTO_AVAILABLE:
            self._load_or_generate()
        else:
            _warn_missing()

    # ── Key management ────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        """Whether this signer can actually sign (a private key is loaded)."""
        return CRYPTO_AVAILABLE and self._private is not None

    def _load_or_generate(self) -> None:
        """Load the keypair from disk, generating a fresh one if none exists."""
        if self.key_path.exists():
            self._load_private(self.key_path.read_bytes())
        else:
            self.generate_keypair()

    def _load_private(self, pem: bytes) -> None:
        """Adopt a PEM-encoded PKCS8 private key and derive its public half."""
        self._private = serialization.load_pem_private_key(pem, password=None)
        self._public = self._private.public_key()
        self._public_b64 = self._public_to_b64(self._public)

    @staticmethod
    def _public_to_b64(public: Any) -> str:
        """Base64 of the raw 32-byte Ed25519 public key (compact for embedding)."""
        raw = public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def generate_keypair(self) -> None:
        """Create a new Ed25519 keypair and write it to ``key_path`` / ``.pub``.

        The private key is PEM/PKCS8 with owner-only permissions (``0o600``); the
        public key is PEM ``SubjectPublicKeyInfo`` for interoperability with
        standard tooling (``openssl``, ``ssh-keygen -i`` style readers).
        """
        if not CRYPTO_AVAILABLE:  # pragma: no cover - guarded by callers
            raise RuntimeError("cannot generate a keypair without 'cryptography'")

        private = Ed25519PrivateKey.generate()
        public = private.public_key()

        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        private_pem = private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.key_path.write_bytes(private_pem)
        os.chmod(self.key_path, 0o600)

        public_pem = public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.key_path.with_suffix(self.key_path.suffix + ".pub").write_bytes(public_pem)

        self._private = private
        self._public = public
        self._public_b64 = self._public_to_b64(public)

    # ── Signing ───────────────────────────────────────────────────────────────
    def sign_entry(
        self, entry: dict[str, Any], prev_hash: str | None = None
    ) -> dict[str, Any]:
        """Return a signed copy of ``entry`` with the chain link applied.

        Adds ``prev_hash`` (this signer's last hash, or the supplied override),
        ``signature`` (base64 Ed25519 over :func:`canonical_bytes`), ``public_key``
        (base64 raw), and ``signed_at`` (UTC ISO 8601). Updates the signer's
        running hash so the next call chains from this entry. If ``cryptography``
        is unavailable the entry is returned unchanged (and unsigned).
        """
        if not self.available:
            _warn_missing()
            return entry

        link = prev_hash if prev_hash is not None else self._last_hash
        signed: dict[str, Any] = {k: v for k, v in entry.items() if k not in _SIGNATURE_FIELDS}
        signed["prev_hash"] = link

        signature = self._private.sign(canonical_bytes(signed))
        signed["signature"] = base64.b64encode(signature).decode("ascii")
        signed["public_key"] = self._public_b64
        signed["signed_at"] = datetime.now(timezone.utc).isoformat()

        self._last_hash = entry_hash(signed)
        return signed

    # ── Verification ──────────────────────────────────────────────────────────
    def verify_entry(self, entry: dict[str, Any]) -> bool:
        """Verify one entry's signature against its embedded public key.

        Returns ``False`` for unsigned entries, a missing key, an unparseable
        signature, or when ``cryptography`` is unavailable — i.e. anything we
        cannot positively confirm is treated as not verified.
        """
        if not CRYPTO_AVAILABLE:
            return False
        signature_b64 = entry.get("signature")
        public_b64 = entry.get("public_key")
        if not signature_b64 or not public_b64:
            return False
        try:
            signature = base64.b64decode(signature_b64)
            public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
            public.verify(signature, canonical_bytes(entry))
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    def verify_trail(self, path: str | Path) -> VerificationResult:
        """Verify every entry in a JSONL audit file: signatures *and* hash chain.

        Walks the file in order. An entry is **verified** only if its signature
        is valid *and* its ``prev_hash`` matches the previous signed entry's hash;
        a bad signature or a broken link counts as **tampered** (the first such
        line is reported). Entries without a signature are counted as **unsigned**
        and reset the chain (a gap can't be cryptographically bridged).
        """
        total = verified = unsigned = tampered = 0
        first_tampered: int | None = None
        chain_intact = True
        prev_hash_expected: str | None = None

        for line_no, entry in _iter_entries(Path(path)):
            total += 1
            if not entry.get("signature"):
                unsigned += 1
                chain_intact = False
                prev_hash_expected = None
                continue

            signature_ok = self.verify_entry(entry)
            chain_ok = entry.get("prev_hash") == prev_hash_expected
            if signature_ok and chain_ok:
                verified += 1
            else:
                tampered += 1
                chain_intact = False
                if first_tampered is None:
                    first_tampered = line_no
            prev_hash_expected = entry_hash(entry)

        return VerificationResult(
            total_entries=total,
            verified=verified,
            unsigned=unsigned,
            tampered=tampered,
            first_tampered_line=first_tampered,
            chain_intact=chain_intact and unsigned == 0,
        )

    def sign_trail(self, path: str | Path) -> int:
        """Retroactively sign a JSONL audit file in place; return entries signed.

        Walks the file in order, (re)signing any entry that is unsigned or whose
        ``prev_hash`` no longer matches the running chain, while leaving entries
        that are already valid *and* correctly linked untouched. The file is
        rewritten atomically (temp file + ``os.replace``). Returns how many
        entries were freshly signed.
        """
        if not self.available:
            _warn_missing()
            return 0

        path = Path(path)
        entries = [entry for _, entry in _iter_entries(path)]
        signed_count = 0
        prev_hash_expected: str | None = None
        rebuilt: list[dict[str, Any]] = []

        for entry in entries:
            already_valid = (
                bool(entry.get("signature"))
                and self.verify_entry(entry)
                and entry.get("prev_hash") == prev_hash_expected
            )
            if already_valid:
                rebuilt.append(entry)
            else:
                signed = self.sign_entry(entry, prev_hash=prev_hash_expected)
                rebuilt.append(signed)
                signed_count += 1
            prev_hash_expected = entry_hash(rebuilt[-1])
            # Keep the running hash aligned with the file we are emitting so a
            # subsequent live append chains from the rewritten tail.
            self._last_hash = prev_hash_expected

        _atomic_write_jsonl(path, rebuilt)
        return signed_count


# ── Module-level helpers ──────────────────────────────────────────────────────
def _iter_entries(path: Path):
    """Yield ``(line_number, entry)`` for each valid JSON line; skip junk lines."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line_no, raw in enumerate(text.splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield line_no, entry


def _atomic_write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    """Write ``entries`` as JSONL to ``path`` atomically via a temp-file rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


# A process-wide signer reused by the live append path, so we don't reload the
# key on every logged action. Reset via :func:`reset_default_signer` in tests.
_default_signer: AuditSigner | None = None


def get_default_signer() -> AuditSigner | None:
    """Return a cached :class:`AuditSigner`, or ``None`` if signing is disabled.

    Used by :func:`eidetic_os.audit.log_action` to sign new entries. Returns
    ``None`` when ``cryptography`` is unavailable so the caller writes the entry
    unsigned without paying for repeated key loads.
    """
    global _default_signer
    if not CRYPTO_AVAILABLE:
        _warn_missing()
        return None
    if _default_signer is None:
        _default_signer = AuditSigner()
    return _default_signer


def reset_default_signer() -> None:
    """Drop the cached default signer (so the next call re-resolves the key path)."""
    global _default_signer
    _default_signer = None


def sign_for_append(entry: dict[str, Any], path: Path) -> dict[str, Any]:
    """Sign ``entry`` so it chains onto the existing trail at ``path``.

    Reads the last signed entry already on disk to derive ``prev_hash``, then
    signs. On any failure — or when signing is unavailable — returns ``entry``
    unchanged so the audit write proceeds (unsigned). This is the single hook
    :func:`eidetic_os.audit.log_action` calls while holding its write lock.
    """
    signer = get_default_signer()
    if signer is None or not signer.available:
        return entry
    try:
        prev_hash: str | None = None
        for _, prior in _iter_entries(path):
            if prior.get("signature"):
                prev_hash = entry_hash(prior)
            else:
                prev_hash = None
        return signer.sign_entry(entry, prev_hash=prev_hash)
    except Exception as exc:  # pragma: no cover - signing must never break logging
        print(f"audit_crypto: failed to sign entry ({exc})", file=sys.stderr)
        return entry
