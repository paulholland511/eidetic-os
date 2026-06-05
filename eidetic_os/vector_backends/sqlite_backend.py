"""The SQLite vector backend — the zero-config default.

This is a thin :class:`~eidetic_os.vector_backend.VectorBackend` adapter over the
existing :class:`eidetic_os.vectordb.VectorStore`. It adds no new storage code: it
simply maps the backend interface onto the store that already powers the RAG
pipeline, so selecting ``VECTOR_BACKEND=sqlite`` (or setting nothing at all)
behaves exactly as Eidetic OS always has. The store accelerates search with the
``sqlite-vec`` extension when present and falls back to a NumPy/pure-Python
cosine scan otherwise — see :mod:`eidetic_os.vectordb`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, final

from eidetic_os.vector_backend import SQLITE, VectorBackend
from eidetic_os.vectordb import VectorStore, open_store


@final
class SQLiteBackend(VectorBackend):
    """A :class:`VectorBackend` backed by a single SQLite database file."""

    name = SQLITE

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    @classmethod
    def open(cls, rag_dir: str | Path) -> SQLiteBackend:
        """Open the store at ``<rag_dir>/vectors.db``, auto-migrating legacy JSON.

        Delegates to :func:`eidetic_os.vectordb.open_store`, which imports an
        existing ``vectors.json`` on first open — so an old install upgrades
        transparently the first time it embeds.
        """
        Path(rag_dir).mkdir(parents=True, exist_ok=True)
        return cls(open_store(rag_dir))

    # ── writes ────────────────────────────────────────────────────────────────
    def insert(self, chunks: list[dict[str, Any]]) -> int:
        return self._store.add_vectors(chunks)

    def delete_by_file(self, file_path: str) -> int:
        return self._store.delete_by_file(file_path)

    def clear(self) -> None:
        self._store.clear()

    # ── reads ─────────────────────────────────────────────────────────────────
    def search(
        self,
        query_vector: Sequence[float],
        k: int = 10,
        filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self._store.search(query_vector, top_k=k, filters=filters)

    def count(self) -> int:
        return self._store.count()

    def files(self) -> list[str]:
        return sorted(self._store.files())

    # ── migration ─────────────────────────────────────────────────────────────
    def export_chunks(self) -> Iterator[dict[str, Any]]:
        yield from self._store.all_chunks(with_embedding=True)

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def close(self) -> None:
        self._store.close()
