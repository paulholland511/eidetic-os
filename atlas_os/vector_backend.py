"""Pluggable vector-storage backends for the Atlas OS RAG pipeline.

The RAG store began life as a single SQLite database (:mod:`atlas_os.vectordb`):
zero-config, dependency-free, and fast enough for a personal vault of tens of
thousands of chunks. As a vault grows — or as people want richer metadata
filtering, on-disk zero-copy scans, or a server-backed index — one storage
engine stops being the right answer for everyone.

This module introduces a thin abstraction so the engine becomes a *choice*:

* :class:`VectorBackend` — the minimal interface every engine implements
  (insert, search, delete-by-file, count, files, clear) plus
  :meth:`~VectorBackend.export_chunks` for backend-to-backend migration.
* :func:`get_backend` — a factory that reads ``VECTOR_BACKEND`` from the
  environment (``sqlite`` | ``lancedb`` | ``chroma``, default ``sqlite``) and
  returns the matching backend rooted at a RAG directory.

The default, :class:`~atlas_os.vector_backends.sqlite_backend.SQLiteBackend`,
wraps the existing :class:`~atlas_os.vectordb.VectorStore`, so nothing changes
for anyone who never sets ``VECTOR_BACKEND``. The optional backends are imported
lazily and depend on extras (``atlas-os[lancedb]`` / ``atlas-os[chroma]``), so
the core install stays slim and importing this module never pulls in a heavy
dependency that may not be installed.

The chunk dicts flowing through :meth:`~VectorBackend.insert` and
:meth:`~VectorBackend.export_chunks` use the same shape the embed pipeline
already produces — ``file``, ``chunk_text``, ``heading``, ``embedding``, and the
optional ``id`` / ``modified_time`` / ``folder`` / ``doc_type`` / ``tags`` — so a
backend is a drop-in for the SQLite store. Search results are dicts with
``file``, ``heading``, ``text``, and a ``score`` in ``0.0–1.0`` (cosine
similarity), identical across every backend.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Final

# The canonical backend names accepted by VECTOR_BACKEND / `get_backend`.
SQLITE: Final = "sqlite"
LANCEDB: Final = "lancedb"
CHROMA: Final = "chroma"
BACKEND_NAMES: Final = (SQLITE, LANCEDB, CHROMA)

# The env var that selects the backend, and the default when it is unset.
BACKEND_ENV_VAR: Final = "VECTOR_BACKEND"
DEFAULT_BACKEND: Final = SQLITE

# The metadata fields carried alongside every chunk, kept in sync with the dicts
# produced by ``scripts/embed_vault.py`` and accepted by ``VectorStore``.
CHUNK_FIELDS: Final = (
    "id", "file", "chunk_text", "heading", "embedding",
    "modified_time", "folder", "doc_type", "tags",
)


class VectorBackend(ABC):
    """The storage contract every vector engine implements.

    Implementations persist chunk embeddings and answer nearest-neighbour
    queries. The interface is deliberately small: it is everything the embed
    pipeline and search need, and everything migration needs to copy a store
    wholesale from one engine to another. Backends are opened against a path
    (a file or directory under the RAG dir) and should create their storage on
    demand so opening a fresh path just works.
    """

    # ── identity ──────────────────────────────────────────────────────────────
    #: The backend's canonical name (one of :data:`BACKEND_NAMES`). Subclasses
    #: override this so :func:`active_backend_name` and ``atlas doctor`` can
    #: report which engine is live without importing the optional deps.
    name: str = ""

    # ── writes ────────────────────────────────────────────────────────────────
    @abstractmethod
    def insert(self, chunks: list[dict[str, Any]]) -> int:
        """Insert chunk dicts (``file`` / ``chunk_text`` / ``embedding`` …).

        An entry whose ``id`` already exists is replaced rather than duplicated,
        so re-embedding a file after :meth:`delete_by_file` never doubles up.
        Returns the number of chunks written.
        """

    @abstractmethod
    def delete_by_file(self, file_path: str) -> int:
        """Delete every chunk belonging to ``file_path``. Returns the count removed."""

    @abstractmethod
    def clear(self) -> None:
        """Remove every chunk from the store (used by a ``--full`` re-embed)."""

    # ── reads ─────────────────────────────────────────────────────────────────
    @abstractmethod
    def search(
        self,
        query_vector: Sequence[float],
        k: int = 10,
        filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the ``k`` chunks most similar to ``query_vector``.

        Each result is a dict with ``file``, ``heading``, ``text``, and a
        ``score`` in ``0.0–1.0`` (cosine similarity). When ``filters`` is given,
        only chunks whose ``folder``, ``doc_type``, or a tag matches *every*
        filter term are considered.
        """

    @abstractmethod
    def count(self) -> int:
        """Number of chunks currently in the store."""

    @abstractmethod
    def files(self) -> list[str]:
        """The distinct file paths currently in the store (sorted, deterministic)."""

    # ── migration ─────────────────────────────────────────────────────────────
    @abstractmethod
    def export_chunks(self) -> Iterator[dict[str, Any]]:
        """Yield every chunk *with* its embedding, in :data:`CHUNK_FIELDS` shape.

        The output is exactly what :meth:`insert` accepts, so migrating a store
        from one backend to another is ``dst.insert(list(src.export_chunks()))``.
        """

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Release any resources (connections, file handles). Default: no-op."""

    def __enter__(self) -> VectorBackend:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def resolve_backend_name(name: str | None = None) -> str:
    """The selected backend name: explicit ``name``, else ``$VECTOR_BACKEND``, else default.

    The value is lower-cased and validated against :data:`BACKEND_NAMES`; an
    unknown name raises ``ValueError`` with the list of valid choices.
    """
    chosen = (name or os.environ.get(BACKEND_ENV_VAR) or DEFAULT_BACKEND).strip().lower()
    if chosen not in BACKEND_NAMES:
        valid = ", ".join(BACKEND_NAMES)
        raise ValueError(f"unknown vector backend {chosen!r} — choose one of: {valid}")
    return chosen


def active_backend_name() -> str:
    """The configured backend name from the environment (never raises; falls back).

    Convenience for display surfaces (``atlas doctor``) that want to report the
    selected backend without constructing it. An invalid ``VECTOR_BACKEND`` is
    reported verbatim with a ``(invalid)`` suffix rather than raising.
    """
    raw = (os.environ.get(BACKEND_ENV_VAR) or DEFAULT_BACKEND).strip().lower()
    return raw if raw in BACKEND_NAMES else f"{raw} (invalid)"


def get_backend(
    rag_dir: str | Path,
    *,
    name: str | None = None,
) -> VectorBackend:
    """Open (creating if needed) the configured vector backend for a RAG directory.

    ``name`` overrides ``$VECTOR_BACKEND`` when given. The backend modules are
    imported lazily here so that selecting ``sqlite`` never imports ``lancedb``
    or ``chromadb`` (and vice versa), and a missing optional dependency surfaces
    as a clear install hint only when that backend is actually requested.
    """
    chosen = resolve_backend_name(name)
    rag = Path(rag_dir)
    if chosen == SQLITE:
        from atlas_os.vector_backends.sqlite_backend import SQLiteBackend
        return SQLiteBackend.open(rag)
    if chosen == LANCEDB:
        from atlas_os.vector_backends.lancedb_backend import LanceDBBackend
        return LanceDBBackend.open(rag)
    from atlas_os.vector_backends.chroma_backend import ChromaBackend
    return ChromaBackend.open(rag)


def migrate(
    source: VectorBackend,
    target: VectorBackend,
    *,
    batch_size: int = 512,
    on_progress: Callable[[int], None] | None = None,
) -> int:
    """Copy every chunk from ``source`` into ``target``; return the number copied.

    Streams the source store in batches (so a large index never has to be held
    in memory all at once) and inserts each batch into the target. ``on_progress``
    — if given — is called with the running copied-count after every batch, for a
    live progress display. The caller is responsible for opening both backends and
    for clearing the target first if a clean copy is wanted.
    """
    copied = 0
    batch: list[dict[str, Any]] = []
    for chunk in source.export_chunks():
        batch.append(chunk)
        if len(batch) >= batch_size:
            copied += target.insert(batch)
            batch = []
            if on_progress is not None:
                on_progress(copied)
    if batch:
        copied += target.insert(batch)
        if on_progress is not None:
            on_progress(copied)
    return copied
