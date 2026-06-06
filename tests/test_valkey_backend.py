"""Tests for the Valkey vector backend, driven by an in-memory fake server.

Valkey is a *server* backend, so unlike the embedded SQLite/LanceDB/Chroma
engines there is nothing to spin up in CI. Instead we inject a ``FakeValkey``
that implements exactly the command surface the backend touches — ``hset`` /
``hget`` / ``hgetall`` / ``delete`` / ``scan_iter`` and the ``FT.CREATE`` /
``FT.SEARCH`` execute_command path — with *real* cosine-KNN math. That makes the
same interface-compliance battery the other backends run (ranking, filtering,
idempotent upsert, export round-trip) genuinely exercise the Valkey mapping,
score inversion and RESP reply parsing, without a live server.
"""

from __future__ import annotations

import math
import re
import struct
from pathlib import Path
from typing import Any

import pytest

from eidetic_os import vector_backend
from eidetic_os.vector_backends.valkey_backend import ValkeyBackend


# ── In-memory fake Valkey ─────────────────────────────────────────────────────
def _b(value: Any) -> bytes:
    return value if isinstance(value, bytes) else str(value).encode()


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """1 − cosine similarity, matching Valkey Search's COSINE DISTANCE_METRIC."""
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - sum(x * y for x, y in zip(a, b)) / (na * nb)


class FakeValkey:
    """A minimal in-memory stand-in for a Valkey server with the Search module."""

    def __init__(self) -> None:
        # key(bytes) -> {field(bytes): value(bytes)}
        self.store: dict[bytes, dict[bytes, bytes]] = {}
        # index name(bytes) -> key prefix(bytes), recorded by FT.CREATE
        self.indexes: dict[bytes, bytes] = {}

    # — hash ops —
    def hset(self, key: Any, mapping: dict[Any, Any]) -> int:
        h = self.store.setdefault(_b(key), {})
        for field, value in mapping.items():
            h[_b(field)] = _b(value)
        return len(mapping)

    def hget(self, key: Any, field: Any) -> bytes | None:
        return self.store.get(_b(key), {}).get(_b(field))

    def hgetall(self, key: Any) -> dict[bytes, bytes]:
        return dict(self.store.get(_b(key), {}))

    def delete(self, *keys: Any) -> int:
        return sum(self.store.pop(_b(k), None) is not None for k in keys)

    def scan_iter(self, match: Any = None):
        prefix = _b(match)[:-1] if match and _b(match).endswith(b"*") else _b(match or b"")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    def close(self) -> None:  # pragma: no cover - lifecycle no-op
        pass

    # — search module —
    def execute_command(self, *args: Any) -> Any:
        cmd = str(args[0]).upper()
        if cmd == "FT.CREATE":
            # FT.CREATE <index> ON HASH PREFIX 1 <prefix> SCHEMA ...
            index, prefix = _b(args[1]), _b(args[6])
            if index in self.indexes:
                raise RuntimeError("Index already exists")
            self.indexes[index] = prefix
            return b"OK"
        if cmd == "FT.SEARCH":
            return self._ft_search(args)
        raise NotImplementedError(cmd)  # pragma: no cover

    def _ft_search(self, args: tuple[Any, ...]) -> list[Any]:
        flat = [str(a) if not isinstance(a, bytes) else a for a in args]
        index = _b(args[1])
        prefix = self.indexes[index]
        query = str(args[2])
        n = int(re.search(r"KNN\s+(\d+)", query).group(1))
        blob = args[flat.index("BLOB") + 1]
        ret_at = flat.index("RETURN")
        ret_count = int(flat[ret_at + 1])
        ret_fields = [str(f) for f in flat[ret_at + 2 : ret_at + 2 + ret_count]]
        query_vec = _unpack(blob)

        scored: list[tuple[float, bytes, dict[bytes, bytes]]] = []
        for key, h in self.store.items():
            if not key.startswith(prefix):
                continue
            dist = _cosine_distance(query_vec, _unpack(h[b"vector"]))
            scored.append((dist, key, h))
        scored.sort(key=lambda t: t[0])

        reply: list[Any] = [len(scored)]
        for dist, key, h in scored[:n]:
            fields: list[bytes] = []
            for name in ret_fields:
                value = str(dist).encode() if name == "__vector_score" else h.get(_b(name), b"")
                fields.extend((name.encode(), value))
            reply.extend((key, fields))
        return reply


# ── Fixtures ──────────────────────────────────────────────────────────────────
def _entries() -> list[dict[str, Any]]:
    return [
        {"id": "a::1", "file": "research/a.md", "chunk_text": "kelly criterion bet sizing",
         "heading": "Kelly", "embedding": [1.0, 0.0, 0.0],
         "folder": "research", "doc_type": "research", "tags": ["trading"]},
        {"id": "b::1", "file": "wiki/b.md", "chunk_text": "totally unrelated content",
         "heading": "", "embedding": [0.0, 1.0, 0.0],
         "folder": "wiki", "doc_type": "wiki", "tags": ["wiki"]},
        {"id": "c::1", "file": "research/c.md", "chunk_text": "kelly sizing revisited",
         "heading": "", "embedding": [0.9, 0.1, 0.0],
         "folder": "research", "doc_type": "research", "tags": ["trading"]},
    ]


@pytest.fixture()
def backend() -> ValkeyBackend:
    return ValkeyBackend(FakeValkey())


@pytest.fixture()
def populated(backend: ValkeyBackend) -> ValkeyBackend:
    backend.insert(_entries())
    return backend


# ── Basics ────────────────────────────────────────────────────────────────────
class TestBasics:
    def test_count_and_files(self, populated: ValkeyBackend) -> None:
        assert populated.count() == 3
        assert populated.files() == ["research/a.md", "research/c.md", "wiki/b.md"]

    def test_insert_returns_count(self, backend: ValkeyBackend) -> None:
        assert backend.insert(_entries()) == 3

    def test_insert_skips_entries_without_embedding(self, backend: ValkeyBackend) -> None:
        added = backend.insert([{"file": "x.md", "chunk_text": "no vector", "embedding": []}])
        assert added == 0
        assert backend.count() == 0

    def test_insert_derives_id_when_missing(self, backend: ValkeyBackend) -> None:
        backend.insert([{"file": "x.md", "chunk_text": "no id field", "embedding": [1.0, 0.0, 0.0]}])
        assert backend.count() == 1
        assert backend.files() == ["x.md"]

    def test_clear_empties_the_store(self, populated: ValkeyBackend) -> None:
        populated.clear()
        assert populated.count() == 0
        assert populated.search([1.0, 0.0, 0.0]) == []

    def test_delete_by_file(self, populated: ValkeyBackend) -> None:
        assert populated.delete_by_file("wiki/b.md") == 1
        assert populated.count() == 2
        assert "wiki/b.md" not in populated.files()
        assert populated.delete_by_file("does/not/exist.md") == 0

    def test_insert_is_idempotent_on_id(self, populated: ValkeyBackend) -> None:
        populated.insert([{
            "id": "a::1", "file": "research/a.md", "chunk_text": "updated text",
            "embedding": [1.0, 0.0, 0.0], "folder": "research",
            "doc_type": "research", "tags": ["trading"],
        }])
        assert populated.count() == 3
        hit = populated.search([1.0, 0.0, 0.0], k=1)[0]
        assert hit["text"] == "updated text"


# ── Search ────────────────────────────────────────────────────────────────────
class TestSearch:
    def test_search_empty_store(self, backend: ValkeyBackend) -> None:
        assert backend.search([1.0, 0.0, 0.0]) == []

    def test_search_ranks_by_similarity(self, populated: ValkeyBackend) -> None:
        results = populated.search([1.0, 0.0, 0.0], k=3)
        assert [r["file"] for r in results] == ["research/a.md", "research/c.md", "wiki/b.md"]
        assert results[0]["score"] > results[1]["score"] > results[2]["score"]

    def test_result_shape(self, populated: ValkeyBackend) -> None:
        top = populated.search([1.0, 0.0, 0.0], k=1)[0]
        assert set(top) == {"file", "heading", "text", "score"}
        assert top["file"] == "research/a.md"
        assert top["heading"] == "Kelly"
        assert 0.99 <= top["score"] <= 1.0

    def test_search_respects_k(self, populated: ValkeyBackend) -> None:
        assert len(populated.search([1.0, 0.0, 0.0], k=2)) == 2

    def test_filters_restrict_candidates(self, populated: ValkeyBackend) -> None:
        results = populated.search([1.0, 0.0, 0.0], k=5, filters=["wiki"])
        assert [r["file"] for r in results] == ["wiki/b.md"]

    def test_tag_filter(self, populated: ValkeyBackend) -> None:
        results = populated.search([1.0, 0.0, 0.0], k=5, filters=["trading"])
        assert {r["file"] for r in results} == {"research/a.md", "research/c.md"}


# ── Export ────────────────────────────────────────────────────────────────────
class TestExport:
    def test_export_roundtrips_fields(self, populated: ValkeyBackend) -> None:
        exported = {c["id"]: c for c in populated.export_chunks()}
        assert set(exported) == {"a::1", "b::1", "c::1"}
        a = exported["a::1"]
        assert a["file"] == "research/a.md"
        assert a["chunk_text"] == "kelly criterion bet sizing"
        assert a["heading"] == "Kelly"
        assert a["folder"] == "research"
        assert a["doc_type"] == "research"
        assert a["tags"] == ["trading"]
        assert [round(x, 3) for x in a["embedding"]] == [1.0, 0.0, 0.0]

    def test_export_empty_store(self, backend: ValkeyBackend) -> None:
        assert list(backend.export_chunks()) == []

    def test_export_feeds_insert(self, populated: ValkeyBackend) -> None:
        # The export shape must be exactly what insert() accepts (migration path).
        target = ValkeyBackend(FakeValkey())
        copied = target.insert(list(populated.export_chunks()))
        assert copied == 3
        assert target.files() == populated.files()


# ── Namespacing & factory ─────────────────────────────────────────────────────
class TestIntegration:
    def test_open_namespaces_index_by_rag_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake = FakeValkey()

        class _Mod:
            @staticmethod
            def from_url(url: str, decode_responses: bool) -> FakeValkey:
                assert decode_responses is False
                return fake

        monkeypatch.setattr(
            "eidetic_os.vector_backends.valkey_backend._require_valkey", lambda: _Mod
        )
        one = ValkeyBackend.open(tmp_path / "vault-one")
        two = ValkeyBackend.open(tmp_path / "vault-two")
        # Distinct RAG dirs get distinct, isolated index names and key prefixes.
        assert one._index != two._index
        assert one._prefix != two._prefix

    def test_valkey_is_a_known_backend(self) -> None:
        assert vector_backend.resolve_backend_name("valkey") == "valkey"
        assert "valkey" in vector_backend.BACKEND_NAMES

    def test_env_selects_valkey(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VECTOR_BACKEND", "Valkey")
        assert vector_backend.resolve_backend_name() == "valkey"
        assert vector_backend.active_backend_name() == "valkey"

    def test_missing_dependency_raises_install_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def _no_valkey(name: str, *args: Any, **kwargs: Any) -> Any:
            if name in {"valkey", "redis"}:
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_valkey)
        from eidetic_os.vector_backends import valkey_backend

        with pytest.raises(RuntimeError, match="pip install 'eidetic-os\\[valkey\\]'"):
            valkey_backend._require_valkey()
