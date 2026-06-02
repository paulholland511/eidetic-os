# Feature: The Knowledge Vault

**Source:** [`schemas/enforce_schemas.py`](../../schemas/enforce_schemas.py),
[`templates/vault-skeleton/`](../../templates/vault-skeleton) ·
**CLI:** `atlas schemas`, `atlas init`

The vault is the heart of Atlas OS: a plain folder of markdown notes that is the
**single source of truth**. Everything else — the RAG index, the graph, the git
history — is derived from it and reproducible. It works with any editor;
Obsidian is optional but the conventions match it.

---

## Structure

Top-level folders carry meaning and drive both the RAG `doc_type` and the
frontmatter schema. `atlas init` lays down a skeleton:

```
your-vault/
├── .claude-index.md        # master index agents read first
├── Operations Dashboard.md # at-a-glance status note
├── Skills Catalog.md        # auto-generated menu of agent skills
└── wiki/
    ├── index.md            # wiki home / coverage index
    ├── hot.md              # append-only "recently changed" cache
    └── log.md              # running activity log
```

Common folders Atlas OS understands: `research`, `projects`, `decisions`,
`guides`, `wiki`, `daily`, `memory`, `learning`, `code-solutions`, `inbox`,
`archive`. You can add your own — see *Customising* below.

---

## Frontmatter schemas

To keep notes consistent enough for reliable RAG indexing and dashboard
rendering, `atlas schemas` enforces a small **YAML frontmatter schema per
top-level folder**.

### How it works

- Each note's top-level folder selects a schema from the `SCHEMAS` dict in
  `enforce_schemas.py`. Folders not in `SCHEMAS` (and any in `SKIP_DIRS`) are
  skipped.
- The schema lists `required` fields and `defaults` for filling gaps.
- **Non-destructive:** it only *adds* missing required fields — it never
  overwrites existing values — and writes atomically.
- **Inference:** `date`/`created`/`updated` come from a `YYYY-MM-DD` filename
  prefix, else the file's mtime. `title` is inferred from the filename
  (date prefix stripped, separators → spaces, title-cased).

Example — `projects/migrate-to-postgres.md` with no frontmatter becomes:

```yaml
---
tags: []
type: note
date: 2026-01-15        # from mtime (no date in filename)
title: Migrate To Postgres
status: active
---
```

The full folder→schema table (required fields and defaults for `research`,
`projects`, `decisions`, `wiki`, `daily`, `memory`, `code-solutions`, …) lives in
[`schemas/frontmatter-schemas.md`](../../schemas/frontmatter-schemas.md).

### Usage

```bash
atlas schemas --dry-run            # preview changes, write nothing
atlas schemas                      # apply
atlas schemas --folder projects    # one folder only
atlas schemas --verbose            # list every file examined
```

---

## Customising

- **Add a folder type:** add a key to the `SCHEMAS` dict in
  `enforce_schemas.py` with its `required` + `defaults`.
- **Stop processing a folder:** add it to `SKIP_DIRS`.
- **Match the RAG doc types:** keep `DOC_TYPE_MAP` in
  [`embed_vault.py`](../../scripts/embed_vault.py) in sync with your folders so
  search filters work (see [rag-search.md](rag-search.md)).

## Relationship to other features

- [RAG search](rag-search.md) embeds vault notes and reads their frontmatter
  `tags`.
- The [knowledge graph](knowledge-graph.md) links notes via `[[wikilinks]]`.
- [Git automation](git-automation.md) versions the vault and categorises commits
  by these same top-level folders.
- The [skills catalog](skills-and-automation.md) note lives in the vault root.

See also: [`docs/SETUP.md`](../SETUP.md) · [`docs/SCRIPTS.md`](../SCRIPTS.md#enforce_schemaspy)
