"""The ChromaDB vector backend.

`Chroma <https://www.trychroma.com/>`_ is a popular open-source embedding
database. Its ``PersistentClient`` keeps a local on-disk index, making it a
familiar option for people who already use Chroma elsewhere or want its
ecosystem (LangChain/LlamaIndex integrations, a server mode to grow into).

It is an *optional* backend: install it with ``pip install 'eidetic-os[chroma]'``.
This module imports ``chromadb`` lazily inside :meth:`ChromaBackend.open`, so the
dependency is only required when ``VECTOR_BACKEND=chroma`` is actually selected.

Chunks become one record per chunk in a ``chunks`` collection: the embedding is
the vector, the chunk text is the document, and the remaining fields ride along
as metadata. Chroma metadata values must be scalars, so ``tags`` is stored as a
JSON string — keeping the any-of filter semantics identical to every other
backend. The collection uses cosine space so distances invert cleanly to the
``0.0–1.0`` similarity score the rest of Eidetic OS expects.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, final

from eidetic_os.vector_backend import CHROMA, VectorBackend

# The on-disk Chroma store lives here, with all chunks in one named collection
# configured for cosine distance.
_DB_DIRNAME = "chroma"
_COLLECTION = "chunks"
_COSINE_METADATA = {"hnsw:space": "cosine"}


def _or_empty(value: Any) -> Any:
    """Return ``value`` unless it is ``None`` — a list/array-safe ``value or []``.

    Chroma returns ``embeddings`` as a NumPy array, whose truthiness is ambiguous,
    so the usual ``value or []`` idiom raises. This narrows on ``None`` only.
    """
    return [] if value is None else value


def _require_chromadb() -> Any:
    """Import and return the ``chromadb`` module, or raise a clear install hint."""
    try:
        import chromadb  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "the 'chroma' backend needs the chromadb package — "
            "install it with: pip install 'eidetic-os[chroma]'"
        ) from exc
    return chromadb


@final
class ChromaBackend(VectorBackend):
    """A :class:`VectorBackend` backed by a persistent local ChromaDB collection."""

    name = CHROMA

    def __init__(self, client: Any) -> None:
        self._client = client
        self._collection = client.get_or_create_collection(
            name=_COLLECTION, metadata=_COSINE_METADATA
        )

    @classmethod
    def open(cls, rag_dir: str | Path) -> ChromaBackend:
        """Open (creating if needed) the persistent Chroma store under ``rag_dir``."""
        chromadb = _require_chromadb()
        db_path = Path(rag_dir) / _DB_DIRNAME
        db_path.mkdir(parents=True, exist_ok=True)
        return cls(chromadb.PersistentClient(path=str(db_path)))

    # ── record mapping ────────────────────────────────────────────────────────
    @staticmethod
    def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
        tags = chunk.get("tags", [])
        tags_json = tags if isinstance(tags, str) else json.dumps(tags)
        return {
            "file":          chunk["file"],
            "heading":       chunk.get("heading", ""),
            "modified_time": float(chunk.get("modified_time", 0) or 0),
            "folder":        chunk.get("folder", ""),
            "doc_type":      chunk.get("doc_type", ""),
            "tags":          tags_json,
        }

    # ── writes ────────────────────────────────────────────────────────────────
    def insert(self, chunks: list[dict[str, Any]]) -> int:
        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for chunk in chunks:
            embedding = chunk.get("embedding")
            if not embedding:
                continue
            file = chunk["file"]
            ids.append(chunk.get("id") or f"{file}::{chunk['chunk_text'][:24]}")
            embeddings.append([float(x) for x in embedding])
            documents.append(chunk["chunk_text"])
            metadatas.append(self._metadata(chunk))
        if not ids:
            return 0
        # upsert dedups by id natively, so a re-embed replaces a file's chunks.
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
        return len(ids)

    def delete_by_file(self, file_path: str) -> int:
        existing = self._collection.get(where={"file": file_path})
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(where={"file": file_path})
        return len(ids)

    def clear(self) -> None:
        self._client.delete_collection(_COLLECTION)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION, metadata=_COSINE_METADATA
        )

    # ── reads ─────────────────────────────────────────────────────────────────
    def search(
        self,
        query_vector: Sequence[float],
        k: int = 10,
        filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        total = self.count()
        if total == 0:
            return []
        # Without filters, ask Chroma for exactly k. With filters, over-fetch and
        # apply the shared any-of-folder/doc_type/tag semantics in Python, then
        # trim — identical results across every backend.
        n = min(total, total if filters else k)
        res = self._collection.query(
            query_embeddings=[list(query_vector)],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        metadatas = (res.get("metadatas") or [[]])[0]
        documents = (res.get("documents") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        results: list[dict[str, Any]] = []
        for meta, doc, dist in zip(metadatas, documents, distances):
            if filters and not _meta_matches_filters(meta, filters):
                continue
            results.append({
                "file":    meta.get("file", ""),
                "heading": meta.get("heading", ""),
                "text":    doc,
                # cosine space → distance is (1 − cosine similarity); invert it.
                "score":   1.0 - float(dist),
            })
            if len(results) >= k:
                break
        return results

    def count(self) -> int:
        return int(self._collection.count())

    def files(self) -> list[str]:
        got = self._collection.get(include=["metadatas"])
        metas = got.get("metadatas") or []
        return sorted({m.get("file", "") for m in metas if m.get("file")})

    # ── migration ─────────────────────────────────────────────────────────────
    def export_chunks(self) -> Iterator[dict[str, Any]]:
        got = self._collection.get(include=["embeddings", "documents", "metadatas"])
        # Chroma hands embeddings back as a NumPy array, so `x or []` would raise
        # ("truth value of an array is ambiguous") — normalise with `is None`.
        ids = _or_empty(got.get("ids"))
        embeddings = _or_empty(got.get("embeddings"))
        documents = _or_empty(got.get("documents"))
        metadatas = _or_empty(got.get("metadatas"))
        for chunk_id, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            try:
                tags = json.loads(meta.get("tags") or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            yield {
                "id":            chunk_id,
                "file":          meta.get("file", ""),
                "chunk_text":    doc,
                "heading":       meta.get("heading", ""),
                "embedding":     list(emb),
                "modified_time": meta.get("modified_time", 0.0),
                "folder":        meta.get("folder", ""),
                "doc_type":      meta.get("doc_type", ""),
                "tags":          tags,
            }


def _meta_matches_filters(meta: dict[str, Any], filters: list[str]) -> bool:
    """True if ALL filter terms match the record's folder, doc_type, or tags."""
    folder = (meta.get("folder") or "").lower()
    doc_type = (meta.get("doc_type") or "").lower()
    try:
        tags = [t.lower() for t in json.loads(meta.get("tags") or "[]")]
    except (json.JSONDecodeError, TypeError):
        tags = []
    for term in filters:
        fl = term.lower()
        if fl not in (folder, doc_type) and fl not in tags:
            return False
    return True
