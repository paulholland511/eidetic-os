# Architecture

Atlas OS is a thin, local-first layer that turns Claude Cowork into a personal
operating system over a markdown knowledge vault. It is deliberately
file-based: the "database" is a folder of `.md` files, the "API" is a set of
small Python scripts, and the "scheduler" is a set of skill prompts run on a
cron-like schedule.

```
                        ┌──────────────────────────────┐
                        │        Claude Cowork           │
                        │  (skills, scheduled tasks,     │
                        │   memory, MCP tools)           │
                        └───────────────┬────────────────┘
                                        │ invokes
            ┌───────────────────────────┼───────────────────────────┐
            ▼                           ▼                            ▼
   ┌─────────────────┐       ┌────────────────────┐       ┌──────────────────┐
   │  scripts/ (py)  │       │  Markdown Vault     │       │  Local LLM        │
   │  embed, graph,  │◀─────▶│  notes / wiki /     │       │  (embeddings +    │
   │  commit, email, │  rw   │  memory / daily     │       │  chat, OpenAI-    │
   │  health, trade  │       │  (git-tracked)      │       │  compatible)      │
   └────────┬────────┘       └────────────────────┘       └─────────┬────────┘
            │                                                        │
            ▼                                                        │
   ┌─────────────────┐                                              │
   │  .rag/          │   vectors.json + graph.json  ◀───────────────┘
   │  vector store   │   (local only, git-ignored)
   └─────────────────┘
```

## Components

### 1. Knowledge vault
A plain folder of markdown notes (works great with Obsidian, but not required).
Top-level folders carry meaning (`research`, `projects`, `decisions`, `memory`,
`wiki`, `daily`, …) and drive the frontmatter schemas. Git-tracked for history.

### 2. RAG pipeline (`scripts/embed_vault.py`, `build_graph.py`)
Chunks notes (~500 tokens, 50 overlap), embeds them via a **local**
OpenAI-compatible endpoint, and stores vectors in `.rag/vectors.json`. Hybrid
search (vector + keyword) at query time. `build_graph.py` derives a wikilink
knowledge graph. Both run incrementally (nightly) and fully (weekly).

### 3. Frontmatter schemas (`schemas/enforce_schemas.py`)
Non-destructive enforcement of per-folder YAML frontmatter so notes stay
consistent. See [`../schemas/frontmatter-schemas.md`](../schemas/frontmatter-schemas.md).

### 4. Scheduled tasks (`skills/*`)
Each is a `SKILL.md` prompt run on a schedule by Claude Cowork: nightly index +
RAG embed, daily reports, weekly health check and full re-embed, etc. They
orchestrate the scripts above and your connected MCP tools. See
[`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md).

### 5. Git automation (`scripts/vault_commit.py`, `vault_changelog.py`)
Auto-commits the vault with categorised messages and produces changelogs for the
morning briefing.

### 6. Email (`scripts/send_email.py`)
A credential-free SMTP sender (password from env) used by the report tasks.

### 7. Trading SDK (`trading/`, optional)
A multi-agent market-research framework that writes briefings into the vault.
Entirely optional and **not financial advice**.

### 8. Dashboard (`dashboard/`)
A static HTML overview that reads from your own local backend endpoints.

## Design principles

- **Local-first.** Notes and embeddings never leave the machine by default.
- **Config via environment.** No paths, hosts, emails, or secrets in code.
- **Files over databases.** Everything is inspectable, diffable, and portable.
- **Idempotent automations.** Re-running a task converges rather than duplicates.
- **Non-destructive.** Scripts add/append; the hot cache is append-only.
