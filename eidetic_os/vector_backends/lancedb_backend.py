"""The LanceDB vector backend.

`LanceDB <https://lancedb.github.io/lancedb/>`_ is an embedded, columnar vector
database built on the Lance format. Compared with the SQLite default it brings:

* **Zero-copy, on-disk scans** — queries memory-map the columnar files instead of
  loading vectors into Python, so a large index stays cheap on RAM.
* **Rich metadata filtering** — a real predicate engine over the metadata
  columns, rather than a Python post-filter.

It is an *optional* backend: install it with ``pip install 'eidetic-os[lancedb]'``.
This module imports ``lancedb`` lazily inside :meth:`LanceDBBackend.open`, so the
dependency is only required when ``VECTOR_BACKEND=lancedb`` is actually selected.

Chunks are stored one row per chunk in a ``chunks`` table whose columns mirror
the SQLite schema (``id``, ``file``, ``chunk_text``, ``heading``, ``vector``,
``modified_time``, ``folder``, ``doc_type``, ``tags``). ``tags`` is held as a
JSON string so the filter semantics match every other backend exactly. The table
is created lazily on the first insert, once the embedding dimension is known.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, final

from eidetic_os.vector_backend import LANCEDB, VectorBackend

# The on-disk LanceDB dataset lives in this sub-directory of the RAG dir, and the
# chunks live in a single named table within it.
_DB_DIRNAME = "lancedb"
_TABLE = "chunks"


def _require_lancedb() -> Any:
    """Import and return the ``lancedb`` module, or raise a clear install hint."""
    try:
        import lancedb  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "the 'lancedb' backend needs the lancedb package — "
            "install it with: pip install 'eidetic-os[lancedb]'"
        ) from exc
    return lancedb


def _sql_quote(value: str) -> str:
    """Quote a string for a LanceDB SQL predicate (single-quote escaped)."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _table_exists(db: Any, name: str) -> bool:
    """Whether ``name`` is a table in ``db`` — ``list_tables`` with a legacy fallback.

    Newer LanceDB deprecates ``table_names()`` in favour of ``list_tables()``;
    prefer the latter when present so we don't emit a DeprecationWarning, while
    still working on older releases.
    """
    lister = getattr(db, "list_tables", None) or db.table_names
    return name in lister()


@final
class LanceDBBackend(VectorBackend):
    """A :class:`VectorBackend` backed by an on-disk LanceDB dataset."""

    name = LANCEDB

    def __init__(self, db: Any) -> None:
        self._db = db
        # Opened lazily: the table only exists once it has been created from the
        # first batch of vectors (LanceDB needs the dimension to fix the schema).
        self._table = db.open_table(_TABLE) if _table_exists(db, _TABLE) else None

    @classmethod
    def open(cls, rag_dir: str | Path) -> LanceDBBackend:
        """Connect to (creating if needed) the LanceDB dataset under ``rag_dir``."""
        lancedb = _require_lancedb()
        db_path = Path(rag_dir) / _DB_DIRNAME
        db_path.mkdir(parents=True, exist_ok=True)
        return cls(lancedb.connect(str(db_path)))

    # ── row mapping ───────────────────────────────────────────────────────────
    @staticmethod
    def _to_row(chunk: dict[str, Any]) -> dict[str, Any] | None:
        """Map an insert chunk dict to a LanceDB row, or ``None`` if it has no vector."""
        embedding = chunk.get("embedding")
        if not embedding:
            return None
        tags = chunk.get("tags", [])
        tags_json = tags if isinstance(tags, str) else json.dumps(tags)
        file = chunk["file"]
        return {
            "id":            chunk.get("id") or f"{file}::{chunk['chunk_text'][:24]}",
            "file":          file,
            "chunk_text":    chunk["chunk_text"],
            "heading":       chunk.get("heading", ""),
            "vector":        [float(x) for x in embedding],
            "modified_time": float(chunk.get("modified_time", 0) or 0),
            "folder":        chunk.get("folder", ""),
            "doc_type":      chunk.get("doc_type", ""),
            "tags":          tags_json,
        }

    @staticmethod
    def _from_row(row: dict[str, Any]) -> dict[str, Any]:
        """Map a stored LanceDB row back to a :data:`CHUNK_FIELDS` export dict."""
        try:
            tags = json.loads(row.get("tags") or "[]")
        except (json.JSONDecodeError, TypeError):
            tags = []
        return {
            "id":            row["id"],
            "file":          row["file"],
            "chunk_text":    row["chunk_text"],
            "heading":       row.get("heading", ""),
            "embedding":     list(row["vector"]),
            "modified_time": row.get("modified_time", 0.0),
            "folder":        row.get("folder", ""),
            "doc_type":      row.get("doc_type", ""),
            "tags":          tags,
        }

    # ── writes ────────────────────────────────────────────────────────────────
    def insert(self, chunks: list[dict[str, Any]]) -> int:
        rows = [r for r in (self._to_row(c) for c in chunks) if r is not None]
        if not rows:
            return 0
        if self._table is None:
            self._table = self._db.create_table(_TABLE, data=rows)
            return len(rows)
        # Upsert-by-id: drop any existing rows with these ids, then append, so a
        # re-embed of a file replaces its chunks instead of duplicating them.
        ids = {r["id"] for r in rows}
        id_list = ", ".join(_sql_quote(i) for i in ids)
        self._table.delete(f"id IN ({id_list})")
        self._table.add(rows)
        return len(rows)

    def delete_by_file(self, file_path: str) -> int:
        if self._table is None:
            return 0
        removed = len(
            self._table.search().where(f"file = {_sql_quote(file_path)}").to_list()
        )
        if removed:
            self._table.delete(f"file = {_sql_quote(file_path)}")
        return removed

    def clear(self) -> None:
        if _table_exists(self._db, _TABLE):
            self._db.drop_table(_TABLE)
        self._table = None

    # ── reads ─────────────────────────────────────────────────────────────────
    def search(
        self,
        query_vector: Sequence[float],
        k: int = 10,
        filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self._table is None or self.count() == 0:
            return []
        # Without filters we let LanceDB's KNN return exactly k. With filters we
        # over-fetch (the whole table) and apply the same any-of-folder/doc_type/
        # tag semantics as the other backends, then trim to k — keeping results
        # identical regardless of engine.
        limit = self.count() if filters else k
        rows = (
            self._table.search(list(query_vector))
            .metric("cosine")
            .limit(limit)
            .to_list()
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            if filters and not _row_matches_filters(row, filters):
                continue
            results.append({
                "file":    row["file"],
                "heading": row.get("heading", ""),
                "text":    row["chunk_text"],
                # metric="cosine" makes _distance a cosine distance; invert it.
                "score":   1.0 - float(row["_distance"]),
            })
            if len(results) >= k:
                break
        return results

    def count(self) -> int:
        return 0 if self._table is None else int(self._table.count_rows())

    def files(self) -> list[str]:
        if self._table is None:
            return []
        rows = self._table.to_arrow().column("file").to_pylist()
        return sorted(set(rows))

    # ── migration ─────────────────────────────────────────────────────────────
    def export_chunks(self) -> Iterator[dict[str, Any]]:
        if self._table is None:
            return
        for row in self._table.to_arrow().to_pylist():
            yield self._from_row(row)


def _row_matches_filters(row: dict[str, Any], filters: list[str]) -> bool:
    """True if ALL filter terms match the row's folder, doc_type, or tags."""
    folder = (row.get("folder") or "").lower()
    doc_type = (row.get("doc_type") or "").lower()
    try:
        tags = [t.lower() for t in json.loads(row.get("tags") or "[]")]
    except (json.JSONDecodeError, TypeError):
        tags = []
    for term in filters:
        fl = term.lower()
        if fl not in (folder, doc_type) and fl not in tags:
            return False
    return True
