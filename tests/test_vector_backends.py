"""Interface-compliance tests for every VectorBackend implementation.

The same battery runs against each backend so they are provably interchangeable:
the SQLite default always runs; the optional LanceDB and ChromaDB backends run
only where their package is installed (``pytest.importorskip`` skips them
otherwise, so the suite stays green on a core-only install / in CI).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from atlas_os import vector_backend
from atlas_os.vector_backend import VectorBackend


def _entries() -> list[dict]:
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


def _make_sqlite(rag_dir: Path) -> VectorBackend:
    from atlas_os.vector_backends.sqlite_backend import SQLiteBackend
    return SQLiteBackend.open(rag_dir)


def _make_lancedb(rag_dir: Path) -> VectorBackend:
    pytest.importorskip("lancedb")
    from atlas_os.vector_backends.lancedb_backend import LanceDBBackend
    return LanceDBBackend.open(rag_dir)


def _make_chroma(rag_dir: Path) -> VectorBackend:
    pytest.importorskip("chromadb")
    from atlas_os.vector_backends.chroma_backend import ChromaBackend
    return ChromaBackend.open(rag_dir)


BACKEND_FACTORIES: dict[str, Callable[[Path], VectorBackend]] = {
    "sqlite": _make_sqlite,
    "lancedb": _make_lancedb,
    "chroma": _make_chroma,
}


@pytest.fixture(params=list(BACKEND_FACTORIES))
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> VectorBackend:
    """A fresh backend per engine. Skips engines whose optional dep is absent."""
    b = BACKEND_FACTORIES[request.param](tmp_path)  # may pytest.skip
    yield b
    b.close()


@pytest.fixture()
def populated(backend: VectorBackend) -> VectorBackend:
    backend.insert(_entries())
    return backend


class TestBasics:
    def test_count_and_files(self, populated: VectorBackend) -> None:
        assert populated.count() == 3
        assert populated.files() == ["research/a.md", "research/c.md", "wiki/b.md"]

    def test_insert_returns_count(self, backend: VectorBackend) -> None:
        assert backend.insert(_entries()) == 3

    def test_insert_skips_entries_without_embedding(self, backend: VectorBackend) -> None:
        added = backend.insert([{"file": "x.md", "chunk_text": "no vector", "embedding": []}])
        assert added == 0
        assert backend.count() == 0

    def test_clear_empties_the_store(self, populated: VectorBackend) -> None:
        populated.clear()
        assert populated.count() == 0
        assert populated.search([1.0, 0.0, 0.0]) == []

    def test_delete_by_file(self, populated: VectorBackend) -> None:
        assert populated.delete_by_file("wiki/b.md") == 1
        assert populated.count() == 2
        assert "wiki/b.md" not in populated.files()
        assert populated.delete_by_file("does/not/exist.md") == 0

    def test_insert_is_idempotent_on_id(self, populated: VectorBackend) -> None:
        # Re-inserting the same id replaces in place rather than duplicating.
        populated.insert([{
            "id": "a::1", "file": "research/a.md", "chunk_text": "updated text",
            "embedding": [1.0, 0.0, 0.0], "folder": "research",
            "doc_type": "research", "tags": ["trading"],
        }])
        assert populated.count() == 3
        hit = populated.search([1.0, 0.0, 0.0], k=1)[0]
        assert hit["text"] == "updated text"


class TestSearch:
    def test_search_empty_store(self, backend: VectorBackend) -> None:
        assert backend.search([1.0, 0.0, 0.0]) == []

    def test_search_ranks_by_similarity(self, populated: VectorBackend) -> None:
        results = populated.search([1.0, 0.0, 0.0], k=3)
        assert [r["file"] for r in results] == ["research/a.md", "research/c.md", "wiki/b.md"]
        assert results[0]["score"] > results[1]["score"] > results[2]["score"]

    def test_result_shape(self, populated: VectorBackend) -> None:
        top = populated.search([1.0, 0.0, 0.0], k=1)[0]
        assert set(top) == {"file", "heading", "text", "score"}
        assert top["file"] == "research/a.md"
        assert top["heading"] == "Kelly"
        assert 0.99 <= top["score"] <= 1.0

    def test_search_respects_k(self, populated: VectorBackend) -> None:
        assert len(populated.search([1.0, 0.0, 0.0], k=2)) == 2

    def test_filters_restrict_candidates(self, populated: VectorBackend) -> None:
        # A query that most resembles research/a.md, filtered to the wiki, must
        # only ever return the wiki chunk.
        results = populated.search([1.0, 0.0, 0.0], k=5, filters=["wiki"])
        assert [r["file"] for r in results] == ["wiki/b.md"]

    def test_tag_filter(self, populated: VectorBackend) -> None:
        results = populated.search([1.0, 0.0, 0.0], k=5, filters=["trading"])
        assert {r["file"] for r in results} == {"research/a.md", "research/c.md"}


class TestExport:
    def test_export_roundtrips_fields(self, populated: VectorBackend) -> None:
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

    def test_export_empty_store(self, backend: VectorBackend) -> None:
        assert list(backend.export_chunks()) == []


class TestFactory:
    def test_default_is_sqlite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        assert vector_backend.resolve_backend_name() == "sqlite"
        assert vector_backend.active_backend_name() == "sqlite"

    def test_env_selects_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VECTOR_BACKEND", "LanceDB")
        assert vector_backend.resolve_backend_name() == "lancedb"

    def test_explicit_name_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VECTOR_BACKEND", "chroma")
        assert vector_backend.resolve_backend_name("sqlite") == "sqlite"

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown vector backend"):
            vector_backend.resolve_backend_name("redis")

    def test_active_name_reports_invalid_without_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VECTOR_BACKEND", "redis")
        assert vector_backend.active_backend_name() == "redis (invalid)"

    def test_get_backend_sqlite(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VECTOR_BACKEND", "sqlite")
        b = vector_backend.get_backend(tmp_path)
        try:
            assert b.name == "sqlite"
        finally:
            b.close()
