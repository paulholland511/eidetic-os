"""The Valkey vector backend.

`Valkey <https://valkey.io/>`_ is the BSD-licensed, community-driven fork of
Redis, and its **Valkey Search** module (the ``FT.*`` command surface forked
from RediSearch) adds an HNSW/FLAT vector index on top of the in-memory store.
Compared with the embedded SQLite default it brings:

* **A shared, server-backed index** — many machines / processes can embed into
  and query the *same* index, instead of each carrying its own on-disk file. The
  vault stops being pinned to one host.
* **In-memory KNN** — vectors live in RAM behind a real ANN index, so queries
  stay fast as the index grows into the hundreds of thousands of chunks.

It is an *optional* backend: install it with ``pip install 'eidetic-os[valkey]'``
(which pulls the ``valkey`` client; the ``redis`` client is accepted as a
drop-in fallback). The client is imported lazily inside :meth:`ValkeyBackend.open`,
so the dependency is only required when ``VECTOR_BACKEND=valkey`` is actually
selected. The server URL comes from ``VALKEY_URL`` (or ``REDIS_URL``), defaulting
to ``redis://localhost:6379``.

Each chunk is stored as a Valkey **HASH** under a per-RAG-dir key prefix, with
the embedding packed as little-endian ``FLOAT32`` bytes in the ``vector`` field
and the remaining fields (``id``, ``file``, ``chunk_text``, ``heading``,
``modified_time``, ``folder``, ``doc_type``, ``tags``) alongside it; ``tags`` is
a JSON string so the any-of filter semantics match every other backend exactly.
A single ``FT.CREATE`` index over the prefix powers KNN search with
``DISTANCE_METRIC COSINE``, so distances invert cleanly to the ``0.0–1.0``
similarity score the rest of Eidetic OS expects. The index is created lazily on
the first insert, once the embedding dimension is known.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, final

from eidetic_os.vector_backend import VALKEY, VectorBackend

# The server URL is read from these env vars (in order), falling back to a local
# Valkey on its default port.
_URL_ENV_VARS = ("VALKEY_URL", "REDIS_URL")
_DEFAULT_URL = "redis://localhost:6379"

# Naming. The index name and key prefix are namespaced per RAG directory so two
# vaults pointed at the same server never collide. The constructor defaults are
# used for direct construction (and tests); `open` derives namespaced values.
_INDEX = "eidetic_chunks_idx"
_KEY_PREFIX = "eidetic:chunk:"

# The KNN score is returned by FT.SEARCH under this alias; with a COSINE metric it
# is the cosine *distance* (1 − similarity), which we invert to a 0.0–1.0 score.
_SCORE_FIELD = "__vector_score"


def _require_valkey() -> Any:
    """Import and return a Valkey client module, or raise a clear install hint.

    Prefers the ``valkey`` package; accepts ``redis`` as a drop-in fallback since
    the two share an API and either can talk to a Valkey server.
    """
    try:
        import valkey  # type: ignore[import-not-found]

        return valkey
    except ImportError:
        pass
    try:
        import redis  # type: ignore[import-not-found]

        return redis
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "the 'valkey' backend needs the valkey (or redis) package — "
            "install it with: pip install 'eidetic-os[valkey]'"
        ) from exc


def _pack(vector: Sequence[float]) -> bytes:
    """Pack a vector as little-endian FLOAT32 bytes (the wire format Valkey Search wants)."""
    return struct.pack(f"<{len(vector)}f", *(float(x) for x in vector))


def _unpack(blob: bytes) -> list[float]:
    """Inverse of :func:`_pack` — decode FLOAT32 bytes back to a list of floats."""
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def _dec(value: Any) -> str:
    """Decode a Valkey field (``bytes``) to ``str``; pass through anything already text."""
    return value.decode() if isinstance(value, bytes) else ("" if value is None else str(value))


@final
class ValkeyBackend(VectorBackend):
    """A :class:`VectorBackend` backed by a Valkey server with the Search module."""

    name = VALKEY

    def __init__(
        self,
        client: Any,
        *,
        index: str = _INDEX,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._client = client
        self._index = index
        self._prefix = key_prefix
        # The FT index is created lazily on the first insert (it needs the vector
        # dimension). `_dim` doubles as the "index exists" flag for this session.
        self._dim: int | None = None

    @classmethod
    def open(cls, rag_dir: str | Path) -> ValkeyBackend:
        """Connect to the Valkey server (``$VALKEY_URL``) for ``rag_dir``.

        The index name and key prefix are namespaced by a stable hash of the
        resolved RAG directory so distinct vaults sharing one server stay
        isolated.
        """
        valkey = _require_valkey()
        url = next((os.environ[v] for v in _URL_ENV_VARS if os.environ.get(v)), _DEFAULT_URL)
        # decode_responses must stay False: the `vector` field is raw FLOAT32
        # bytes and would be corrupted by a utf-8 decode. Text fields are decoded
        # explicitly via `_dec`.
        client = valkey.from_url(url, decode_responses=False)
        slug = hashlib.sha1(str(Path(rag_dir).resolve()).encode()).hexdigest()[:12]
        return cls(client, index=f"eidetic_chunks_{slug}", key_prefix=f"eidetic:{slug}:chunk:")

    # ── helpers ─────────────────────────────────────────────────────────────────
    def _key(self, chunk_id: str) -> str:
        return f"{self._prefix}{chunk_id}"

    def _scan(self) -> Iterator[bytes]:
        """Yield every chunk key under this backend's prefix."""
        yield from self._client.scan_iter(match=f"{self._prefix}*")

    def _ensure_index(self, dim: int) -> None:
        """Create the FT vector index once the dimension is known (idempotent)."""
        if self._dim is not None:
            return
        try:
            # Only the vector is indexed server-side; folder/doc_type/tag filtering
            # is applied in Python (over-fetch + any-of) so semantics match every
            # other backend exactly regardless of engine.
            self._client.execute_command(
                "FT.CREATE", self._index, "ON", "HASH",
                "PREFIX", "1", self._prefix,
                "SCHEMA",
                "vector", "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32", "DIM", str(dim), "DISTANCE_METRIC", "COSINE",
            )
        except Exception:  # noqa: BLE001 - index already exists is the expected case
            pass
        self._dim = dim

    # ── writes ────────────────────────────────────────────────────────────────
    def insert(self, chunks: list[dict[str, Any]]) -> int:
        rows = [c for c in chunks if c.get("embedding")]
        if not rows:
            return 0
        self._ensure_index(len(rows[0]["embedding"]))
        for chunk in rows:
            file = chunk["file"]
            chunk_id = chunk.get("id") or f"{file}::{chunk['chunk_text'][:24]}"
            tags = chunk.get("tags", [])
            tags_json = tags if isinstance(tags, str) else json.dumps(tags)
            # A HASH keyed by the deterministic id means re-embedding a file
            # overwrites its chunks in place rather than duplicating them.
            self._client.hset(self._key(chunk_id), mapping={
                "id":            chunk_id,
                "file":          file,
                "chunk_text":    chunk["chunk_text"],
                "heading":       chunk.get("heading", ""),
                "vector":        _pack(chunk["embedding"]),
                "modified_time": str(float(chunk.get("modified_time", 0) or 0)),
                "folder":        chunk.get("folder", ""),
                "doc_type":      chunk.get("doc_type", ""),
                "tags":          tags_json,
            })
        return len(rows)

    def delete_by_file(self, file_path: str) -> int:
        keys = [k for k in self._scan() if _dec(self._client.hget(k, "file")) == file_path]
        if keys:
            self._client.delete(*keys)
        return len(keys)

    def clear(self) -> None:
        keys = list(self._scan())
        if keys:
            self._client.delete(*keys)

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
        # Without filters, ask the index for exactly k. With filters, over-fetch
        # (the whole index) and apply the shared any-of-folder/doc_type/tag
        # semantics in Python, then trim — identical results across every backend.
        n = total if filters else min(k, total)
        raw = self._client.execute_command(
            "FT.SEARCH", self._index,
            f"*=>[KNN {n} @vector $BLOB AS {_SCORE_FIELD}]",
            "PARAMS", "2", "BLOB", _pack(query_vector),
            "RETURN", "7",
            "file", "heading", "chunk_text", "folder", "doc_type", "tags", _SCORE_FIELD,
            "SORTBY", _SCORE_FIELD,
            "DIALECT", "2",
        )
        results: list[dict[str, Any]] = []
        for fields in _iter_docs(raw):
            if filters and not _matches_filters(fields, filters):
                continue
            results.append({
                "file":    fields.get("file", ""),
                "heading": fields.get("heading", ""),
                "text":    fields.get("chunk_text", ""),
                # COSINE metric → the score field is a cosine distance; invert it.
                "score":   1.0 - float(fields.get(_SCORE_FIELD, "1")),
            })
            if len(results) >= k:
                break
        return results

    def count(self) -> int:
        return sum(1 for _ in self._scan())

    def files(self) -> list[str]:
        return sorted({
            _dec(file)
            for k in self._scan()
            if (file := self._client.hget(k, "file"))
        })

    # ── migration ─────────────────────────────────────────────────────────────
    def export_chunks(self) -> Iterator[dict[str, Any]]:
        for key in self._scan():
            row = {_dec(field): value for field, value in self._client.hgetall(key).items()}
            try:
                tags = json.loads(_dec(row.get("tags")) or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            yield {
                "id":            _dec(row.get("id")),
                "file":          _dec(row.get("file")),
                "chunk_text":    _dec(row.get("chunk_text")),
                "heading":       _dec(row.get("heading")),
                "embedding":     _unpack(row["vector"]),
                "modified_time": float(_dec(row.get("modified_time")) or 0.0),
                "folder":        _dec(row.get("folder")),
                "doc_type":      _dec(row.get("doc_type")),
                "tags":          tags,
            }

    # ── lifecycle ───────────────────────────────────────────────────────────────
    def close(self) -> None:
        closer = getattr(self._client, "close", None)
        if callable(closer):
            closer()


def _iter_docs(raw: Sequence[Any]) -> Iterator[dict[str, str]]:
    """Yield each FT.SEARCH document as a decoded ``{field: value}`` dict.

    The RESP2 reply is ``[total, key1, [f, v, f, v, …], key2, [...], …]`` — we skip
    the leading count and every key, keeping the flat field/value list per doc.
    """
    if not raw:
        return
    items = list(raw[1:])
    for i in range(1, len(items), 2):  # items[0,2,…] are keys; items[1,3,…] are field-lists
        flat = items[i]
        yield {_dec(flat[j]): _dec(flat[j + 1]) for j in range(0, len(flat) - 1, 2)}


def _matches_filters(fields: dict[str, str], filters: list[str]) -> bool:
    """True if ALL filter terms match the doc's folder, doc_type, or tags."""
    folder = (fields.get("folder") or "").lower()
    doc_type = (fields.get("doc_type") or "").lower()
    try:
        tags = [t.lower() for t in json.loads(fields.get("tags") or "[]")]
    except (json.JSONDecodeError, TypeError):
        tags = []
    for term in filters:
        fl = term.lower()
        if fl not in (folder, doc_type) and fl not in tags:
            return False
    return True
