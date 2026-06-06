# Dev.to

**Title:** How I Built a Personal AI Operating System with Claude, Python, and Local LLMs

**Tags:** #ai #python #opensource #rag

---

> *Add a hero image / architecture diagram here — see the ASCII version below for what to draw.*

Claude is a brilliant assistant with one fatal flaw for daily work: it's stateless. Close the tab and the context is gone. Last week's research, yesterday's planning, the reasoning behind a decision — all of it evaporates at the session boundary.

I got tired of re-explaining myself, so I built a configuration layer that fixes it. It's called **Eidetic OS** — an open-source, local-first "operating system" that turns Claude into something that remembers everything and runs work autonomously while I'm away. Here's how it's put together and the decisions behind it.

## What it actually does

Three things, composably:

1. **Captures every conversation** back into a markdown vault as a searchable note, twice a day.
2. **Indexes that vault** with a local RAG pipeline so you can retrieve anything by meaning.
3. **Runs scheduled tasks autonomously** — nightly indexing, morning briefings, email reports.

The result is a "second brain" that gets smarter the more you use it, and runs entirely on your own machine.

## The architecture

```
            ┌──────────────────────────────┐
            │        Claude Cowork          │
            │  skills · scheduled tasks ·   │
            │  memory · MCP tools           │
            └───────────────┬───────────────┘
                            │ invokes
     ┌──────────────────────┼──────────────────────┐
     ▼                      ▼                      ▼
┌──────────┐      ┌──────────────────┐     ┌──────────────┐
│ eidetic CLI│◀─rw─▶│  Markdown vault   │     │  Local LLM    │
│ (Python) │      │  notes · git      │     │  embed + chat │
└────┬─────┘      └──────────────────┘     └──────┬───────┘
     ▼                                            │
┌──────────┐    vectors.db + graph.json  ◀────────┘
│  .rag/   │    (SQLite, git-ignored, reproducible)
└──────────┘
```

The vault is the **source of truth**. Everything in `.rag/` is derived and reproducible — back up your markdown and your secrets, rebuild the rest. Config lives entirely in environment variables; there are no paths, hosts, or secrets in code.

## Key decisions

**Why SQLite for vectors, not a vector DB.** I started with a single `vectors.json` and it didn't scale. I moved to a SQLite store (`vectors.db`) that uses the `sqlite-vec` KNN index when the extension is available and falls back to a NumPy cosine scan when it isn't. SQLite gave me incremental insert/delete, per-file/per-batch checkpointing (an interrupted embed resumes instead of restarting), and zero infrastructure — no daemon, no Docker, just a file. For a personal-scale knowledge base that's exactly the right trade-off.

**Why hybrid search, not pure vectors.** Pure vector search misses exact-match terms (a function name, a ticker, an acronym). Pure keyword search misses paraphrase. So I fuse both: Okapi BM25 lexical ranking and vector ranking combined with **Reciprocal Rank Fusion**, then reranked by TF-IDF cosine to the query. Chunking is semantic — split on heading/paragraph boundaries up to a token budget rather than blind character windows — and there's an embedding cache keyed by `(model, text)` so a full rebuild skips unchanged chunks.

```python
# Hybrid retrieval, conceptually:
vector_hits  = vector_search(query_embedding, top_k=50)
keyword_hits = bm25_search(query, top_k=50)
fused        = reciprocal_rank_fusion(vector_hits, keyword_hits)
results      = rerank_by_tfidf(fused, query)[:top_k]
```

**Why Flask, not React.** The dashboard reads from the same Python modules the CLI uses, so the UI is a thin presentation layer over logic that's already tested. A React SPA would have meant a second codebase, a build step, and an API contract to keep in sync — all to display seven panels of mostly-static data. Server-rendered Flask was less code, fewer moving parts, and `pip install 'eidetic-os[dashboard]'` away. Boring on purpose.

**Why pluggable local LLMs.** It auto-detects LM Studio, Ollama, llama.cpp, or any OpenAI-compatible endpoint (probed in that order). Embeddings run against `nomic-embed-text`; chat against whatever you've loaded. No API keys for the core features, and nothing leaves the machine unless you wire up an external endpoint yourself.

## What the CLI looks like

```bash
eidetic init                       # interactive setup, scaffolds + git-inits a vault
eidetic backends                   # what local LLM is reachable?
eidetic embed --incremental        # embed only what changed since last run
eidetic search "kelly criterion sizing" --folder research --top-k 10
eidetic graph --open               # D3 force-directed knowledge graph in the browser
eidetic dashboard                  # Flask UI, seven live panels
eidetic audit show                 # append-only JSONL log of every autonomous action
```

The unit of work is a **skill** — a Claude Cowork prompt that runs on a schedule and orchestrates the Python tooling. That's the line between *chatting with your notes* and *running an operating system over them*. There's a catalogue of 160+ of them installable with one command.

## What I learned

- **Boring infrastructure wins for personal tools.** A folder of markdown + SQLite + git beats a "real" stack because it's diffable, portable, and survives me losing interest in maintaining it. Everything is inspectable.
- **Hybrid retrieval is worth the complexity.** The quality jump from vector-only to BM25 + RRF + rerank was the single biggest improvement in how useful the search felt.
- **Local-first changes what you're willing to store.** When the embeddings never leave your disk, you stop self-censoring what you put in the vault — and that's exactly what makes the retrieval valuable.
- **Make it degrade gracefully.** With no LLM running, vault management, git automation, and keyword search still work. Don't make the whole system depend on the one optional piece.

## Try it

It's MIT licensed, has 400+ tests and CI, and is on PyPI:

```bash
pip install eidetic-os      # or pipx / uv tool install
```

**GitHub:** https://github.com/paulholland511/eidetic-os

Next up is an extension architecture that splits a lean core from the domain verticals, making the skill framework speak **MCP** (each skill an MCP server), and a sandboxed security gate that runs AST static analysis on community skills before install. Contributions and feedback very welcome — especially on the retrieval design.
