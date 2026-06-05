# Frontmatter Schemas

Eidetic OS keeps the vault consistent enough for reliable RAG indexing and
dashboard rendering by enforcing a small YAML frontmatter schema **per
top-level folder**. The enforcer (`enforce_schemas.py`) scans notes, validates
their frontmatter against the schema for their folder, and fills in missing
required fields with sensible defaults — inferring `date` and `title` from the
filename where it can.

It is **non-destructive**: it only *adds* missing fields, never overwrites
existing values, and writes atomically.

## How it works

- Each note's top-level folder selects a schema from the `SCHEMAS` dict in `enforce_schemas.py`.
- `required` lists fields that must be present.
- `defaults` supplies values for missing fields (lists, strings, bools, ints).
- `date`/`created`/`updated` are inferred from a `YYYY-MM-DD` filename prefix, else file mtime.
- `title` is inferred from the filename (date prefix stripped, separators → spaces, title-cased).
- Folders not in `SCHEMAS` (and any in `SKIP_DIRS`) are skipped.

## Default schemas

| Folder | Required fields | Notable defaults |
|---|---|---|
| `research` | tags, type, date | type=note, status=draft |
| `research-archive` | tags, type, date | status=archived |
| `code-solutions` | title, date, type, tags, author, commit, complexity, files_changed, indexed | author=Eidetic, indexed=true |
| `memory` | tags, date | type=session-log |
| `memory-archive` | tags, date | type=session-log |
| `learning` | tags, date, type | type=concept-extraction |
| `system` | tags, type, date | type=note |
| `projects` | tags, type, date, title, status | status=active |
| `decisions` | tags, type, date, title | type=decision, status=draft |
| `guides` | tags, type, date, title | type=guide |
| `wiki` | type, title, created, updated, tags, status | type=reference, status=seed |
| `daily` | date, tags, type | type=synthesis |
| `inbox` | tags, type, date | type=note |
| `archive` | tags, type, date | type=note |

For `memory` / `memory-archive`, an `updated` field satisfies the `date`
requirement.

## Example

A note at `projects/migrate-to-postgres.md` with no frontmatter becomes:

```yaml
---
tags: []
type: note
date: 2026-01-15        # from mtime (no date in filename)
title: Migrate To Postgres
status: active
---
```

## Customising

Edit the `SCHEMAS` dict to match your own folder layout. To add a folder, add a
key with `required` and `defaults`. To stop processing a folder, add it to
`SKIP_DIRS`.

## Usage

```bash
export VAULT_PATH=~/Documents/Obsidian/MyVault

python3 enforce_schemas.py --dry-run            # preview changes
python3 enforce_schemas.py                      # apply
python3 enforce_schemas.py --folder projects    # one folder only
python3 enforce_schemas.py --verbose            # show every file
```
