# Feature: Pluggable Vector Backends

**Source:** [`atlas_os/vector_backend.py`](../../atlas_os/vector_backend.py),
[`atlas_os/vector_backends/`](../../atlas_os/vector_backends/) ·
**CLI:** `atlas migrate-vectors --to <backend>`, `atlas doctor` ·
**Config:** `VECTOR_BACKEND` (default `sqlite`) ·
**Store:** `$RAG_DIR/` (`vectors.db` / `lancedb/` / `chroma/`)

The RAG store began as a single, zero-config **SQLite** database — fast and
dependency-free for a personal vault. As a vault grows, or as you want on-disk
zero-copy scans or a different ecosystem, the storage engine should be a
**choice**, not a hard-coded assumption. Atlas OS now puts a thin interface in
front of the store so you can swap the engine without touching the pipeline.

Nothing changes if you do nothing: the default is still SQLite, with no new
dependencies. The alternative backends are **optional extras**, imported lazily,
so the core install stays slim.

---

## Backends at a glance

| Backend   | `VECTOR_BACKEND` | Install                          | Storage             | Best for |
|-----------|------------------|----------------------------------|---------------------|----------|
| SQLite    | `sqlite` (default) | built in (`[vector]` accelerates) | `$RAG_DIR/vectors.db` | Everyone — zero config |
| LanceDB   | `lancedb`        | `pip install 'atlas-os[lancedb]'` | `$RAG_DIR/lancedb/` | Large indexes: columnar, on-disk, zero-copy scans |
| ChromaDB  | `chroma`         | `pip install 'atlas-os[chroma]'`  | `$RAG_DIR/chroma/`  | Chroma users / ecosystem integrations |

All three are interchangeable: the same chunk dicts go in, and search returns the
same `{file, heading, text, score}` shape with `score` a cosine similarity in
`0.0–1.0`. Metadata filtering (`--folder` / `--tag` / `--doc-type`) behaves
identically — every backend applies the same any-of semantics.

---

## How it works

### The interface

[`VectorBackend`](../../atlas_os/vector_backend.py) is a small ABC every engine
implements:

```python
class VectorBackend(ABC):
    def insert(self, chunks: list[dict]) -> int: ...        # upsert by id
    def search(self, query_vector, k=10, filters=None) -> list[dict]: ...
    def delete_by_file(self, file_path: str) -> int: ...
    def count(self) -> int: ...
    def files(self) -> list[str]: ...
    def clear(self) -> None: ...
    def export_chunks(self) -> Iterator[dict]: ...          # for migration
```

- **SQLite** ([`sqlite_backend.py`](../../atlas_os/vector_backends/sqlite_backend.py))
  wraps the existing [`VectorStore`](../../atlas_os/vectordb.py) — `sqlite-vec`
  KNN when the extension is present, NumPy/pure-Python cosine otherwise.
- **LanceDB** ([`lancedb_backend.py`](../../atlas_os/vector_backends/lancedb_backend.py))
  stores one row per chunk in a `chunks` table and queries with cosine distance.
- **ChromaDB** ([`chroma_backend.py`](../../atlas_os/vector_backends/chroma_backend.py))
  uses a persistent local collection configured for cosine space.

### Selection

`get_backend(rag_dir)` reads `VECTOR_BACKEND` (or an explicit `name=`),
validates it against `sqlite | lancedb | chroma`, and constructs the matching
backend — importing the optional dependency lazily, so selecting `sqlite` never
pulls in `lancedb`/`chromadb` and a missing extra surfaces as a clear install
hint only when that backend is actually requested.

> **Note on naming.** This sits in `atlas_os/vector_backends/`, deliberately
> separate from the pre-existing `atlas_os/backends.py`, which detects *LLM*
> backends (LM Studio, Ollama, …) — a different axis entirely.

---

## Switching backends

1. **Install the extra** for your target engine:

   ```bash
   pip install 'atlas-os[lancedb]'    # or [chroma]
   ```

2. **Migrate your existing store** into it — streamed in batches, with progress
   and a count check:

   ```bash
   atlas migrate-vectors --to lancedb
   #   migrating 21430 vector(s): sqlite → lancedb…
   #     21430/21430 copied
   # ✓ migrated 21430 vector(s): sqlite → lancedb (verified 21430).
   #   set VECTOR_BACKEND=lancedb in your .env to use the new store.
   ```

   - `--from <backend>` sets the source (defaults to `$VECTOR_BACKEND`, else
     `sqlite`).
   - `--force` overwrites a non-empty target.
   - The migration **verifies the target count matches the source** and fails
     loudly if it doesn't, so a half-copied store never goes unnoticed.

3. **Record the choice** in `.env`:

   ```bash
   VECTOR_BACKEND=lancedb
   ```

4. **Confirm** with `atlas doctor` — the RAG section reports the configured
   backend:

   ```
   RAG
   ✓ Backend      lancedb
   ✓ Index        /…/.rag/vectors.db
   ```

The source store is left in place, so you can verify before deleting it.

---

## Programmatic use

Anything embedding or querying programmatically should go through the factory so
it honours `VECTOR_BACKEND`:

```python
from atlas_os.vector_backend import get_backend

with get_backend(rag_dir) as store:        # reads VECTOR_BACKEND (default sqlite)
    store.insert(chunks)
    hits = store.search(query_vector, k=10, filters=["research"])
```

---

## Scope & limitations

- **What `VECTOR_BACKEND` drives today.** It selects the engine returned by
  `get_backend()` — which powers `atlas migrate-vectors --to`, `atlas doctor`
  reporting, and any programmatic use. The bundled `atlas embed` / `atlas search`
  pipeline still reads and writes the **SQLite** store directly (its hybrid BM25 +
  rerank path uses store internals beyond the `VectorBackend` interface); routing
  that pipeline through the selected backend is the natural follow-up. So a
  backend switch is **migrate + use via the factory**, not an automatic re-wire of
  the embed/search CLI.
- **No automatic conversion on switch.** Setting `VECTOR_BACKEND` never copies
  your data — run `atlas migrate-vectors --to <backend>` first.
- **Filtered search** over LanceDB/Chroma over-fetches and applies the shared
  any-of-folder/doc_type/tag filter in Python, so results match SQLite exactly
  (at the cost of scanning more candidates for filtered queries).
- The default remains **SQLite with zero dependencies** — the alternative
  backends exist for scale and preference, not as a requirement.
