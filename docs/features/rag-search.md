# Feature: Local RAG Search

**Source:** [`scripts/embed_vault.py`](../../scripts/embed_vault.py) ·
**CLI:** `atlas embed` · **Store:** `$RAG_DIR/vectors.json`

Atlas OS turns your markdown vault into a searchable knowledge base by chunking
each note, embedding the chunks with a **local** OpenAI-compatible model, and
storing the vectors in a plain JSON file on disk. Search combines vector
similarity with keyword matching. Nothing leaves your machine.

---

## How it works

### 1. File discovery

`os.walk` over `VAULT_PATH`, pruning `SKIP_DIRS = {.obsidian, .git, .rag,
.claude}`. It collects every `.md` file, and — if [`pdfplumber`](https://github.com/jsvine/pdfplumber)
is installed — every `.pdf` too. PDF text is extracted page-by-page; scanned or
empty PDFs (no extractable text) are skipped with a warning.

### 2. Chunking

Each document is split into **overlapping chunks** by `chunk_text()`:

- Target size **500 tokens**, **50-token overlap** (`CHUNK_TOKENS`,
  `OVERLAP_TOKENS`). Tokens are approximated as `len(text) // 4` characters
  (`CHARS_PER_TOK = 4`), so a chunk is ~2000 characters with ~200 overlap.
- Every chunk records the **nearest preceding markdown heading** (`#`–`######`)
  as a `heading` field, so a result can show which section it came from.
- Chunks slide forward by `chunk_chars − overlap_chars`; the overlap preserves
  context across boundaries.

### 3. Metadata

For each chunk, the pipeline attaches:

| Field | Source |
|---|---|
| `file` | path relative to the vault |
| `heading` | nearest preceding heading |
| `folder` | first-level folder (`""` for vault-root files) |
| `doc_type` | mapped from the folder via `DOC_TYPE_MAP` (e.g. `research`→`research`, `daily`→`daily`, PDFs→`pdf`, unknown→`misc`) |
| `tags` | parsed from the note's YAML frontmatter (`tags: [a, b]` **or** block list form) |
| `modified_time` | file mtime |

### 4. Embedding

`embed()` POSTs batches of chunk texts to `EMBED_URL`
(default `http://$EMBED_HOST:$EMBED_PORT/v1/embeddings`) with
`{"model": EMBED_MODEL, "input": [...]}`. Behaviour:

- **Batched** — `--batch-size` chunks per request (default **40**).
- **Resilient** — up to 5 attempts with exponential backoff; honours HTTP 429
  rate-limit responses; a 0.05s delay between calls.
- **Auth optional** — sends `Authorization: Bearer $EMBED_API_KEY` only if the
  key is set (local servers usually need none).

Each embedded chunk becomes a vector record:

```json
{
  "id": "research/note.md::12",
  "file": "research/note.md",
  "chunk_text": "…",
  "heading": "Background",
  "embedding": [0.0123, -0.045, …],
  "modified_time": 1717372800.0,
  "folder": "research",
  "doc_type": "research",
  "tags": ["ml", "rag"]
}
```

The whole list is written **atomically** (`.json.tmp` → `os.replace`) to
`vectors.json`.

### 5. Graph rebuild

After a `--full` or `--incremental` run (not `--test`/`--folder`/`--pdfs-only`),
the pipeline dynamically imports [`build_graph.py`](../../scripts/build_graph.py)
and rebuilds `graph.json`. See [knowledge-graph.md](knowledge-graph.md).

---

## Run modes

| Command | Behaviour |
|---|---|
| `atlas embed --full` | Re-embed **everything** from scratch, then rebuild the graph. |
| `atlas embed --incremental` | Embed only files with `mtime` newer than the last run (`last_embed.txt`); resumable via checkpoints. |
| `atlas embed --test N` | Embed the first `N` files only — a fast endpoint/connectivity check. Merges into the existing store. |
| `atlas embed --folder NAME` | Embed only files under top-level folder `NAME`. Merges into the existing store. |
| `atlas embed --pdfs-only` | Embed only PDF files (full pass over PDFs). |

Modifiers: `--checkpoint-interval N` (default 50), `--batch-size N` (default 40).

**Incremental merge semantics.** For incremental / test / folder / pdfs-only
runs, the pipeline loads the existing store, drops the vectors of files it's
about to re-embed (so they don't duplicate), embeds the touched files, and
writes the union. `--full` starts from an empty store.

### Checkpointing & resume

During an incremental run the pipeline writes `embed_checkpoint.json` every
`--checkpoint-interval` chunks (and saves the partial vector store). If the run
is interrupted, the next `--incremental` run reads the checkpoint, skips files
already completed, and resumes — so a large embed never has to start over. The
checkpoint is deleted on clean completion. `last_embed.txt` (with a
`last_embed_fallback.txt` backup) records the run timestamp that drives
incremental selection.

---

## Search

`search(query, top_k=5, mode="hybrid", filters=None)` supports three modes:

- **`vector`** — embed the query, rank all chunks by **cosine similarity**.
- **`keyword`** — term-frequency of the query words in each chunk, normalised to
  0–1.
- **`hybrid`** (default) — take the top 20 from each, then combine:
  **`score = 0.7 × vector + 0.3 × keyword`**, re-rank, return `top_k`.

**Filters.** Pass terms that must *all* match a chunk's `folder`, `doc_type`, or
`tags` (e.g. restrict to `research` notes tagged `rag`).

> The shipped script focuses on building the store; the `search()` function is
> the programmatic entry point used by tooling/skills. The Obsidian RAG search
> CLI referenced in the user `CLAUDE.md` (`obsidian-search.sh`) is one such
> consumer.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_PATH` | — (**required**) | vault to embed |
| `RAG_DIR` | `$VAULT_PATH/.rag` | where `vectors.json` etc. live |
| `EMBED_HOST` / `EMBED_PORT` | `localhost` / `5555` | embeddings endpoint |
| `EMBED_URL` | `…/v1/embeddings` | full override for non-standard paths |
| `EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | model name |
| `EMBED_API_KEY` | `""` | bearer token, if required |

Files written under `RAG_DIR`: `vectors.json`, `last_embed.txt`,
`last_embed_fallback.txt`, `embed_checkpoint.json`, and (via the graph step)
`graph.json`. **All are git-ignored** — derived data, reproducible from the
vault.

---

## Tuning & extending

- **Chunk size / overlap** — edit `CHUNK_TOKENS` / `OVERLAP_TOKENS`.
- **Folder → doc_type** — edit `DOC_TYPE_MAP` to match your vault's folders.
- **Throughput** — raise `--batch-size` if your endpoint handles it; lower
  `INTER_CALL_DELAY` for local servers.
- **Hybrid weighting** — change the `0.7 / 0.3` split in `search()`.

## Troubleshooting

- *Embeddings unreachable* — `curl http://$EMBED_HOST:$EMBED_PORT/v1/models`;
  set `EMBED_URL` if the path differs.
- *PDFs skipped* — install `pdfplumber` (`atlas-os[pdf]`); scanned PDFs need OCR
  first.
- *Stale results* — run `atlas embed --incremental` (nightly task automates it).

See also: [knowledge-graph.md](knowledge-graph.md) ·
[knowledge-vault.md](knowledge-vault.md) ·
[`docs/SCRIPTS.md`](../SCRIPTS.md#embed_vaultpy)
