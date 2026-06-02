# Feature: Git Automation

**Source:** [`scripts/vault_commit.py`](../../scripts/vault_commit.py),
[`scripts/vault_changelog.py`](../../scripts/vault_changelog.py) ·
**CLI:** `atlas commit`, `atlas changelog`

Your vault is its own git repository. Atlas OS keeps a clean, traceable history
of it automatically: a nightly **categorised commit**, and a **changelog** that
reports what changed over any window (the basis for a morning briefing).

Both require `VAULT_PATH` to point at a git repo and run all git commands with
`cwd=VAULT_PATH`.

---

## `atlas commit` — categorised auto-commit

### How it works

1. **Self-heals first:** runs `git worktree prune` and deletes a stale
   `.git/index.lock` if present (so a crashed prior run can't block it).
2. **Reads status** via `git status --porcelain -u`, classifying each path into
   **new** (untracked), **modified**, or **deleted** (renames keep the new path,
   counted as modified).
3. **Nothing to commit?** If all three buckets are empty, it reports "clean" and
   exits 0 without committing.
4. **Categorises** the change set by the **top-level folder** of each changed
   path (not by counts):

   | Folder(s) | Tag |
   |---|---|
   | `daily` | `session-log` |
   | `research`, `wiki` | `research` |
   | `system`, `scripts`, `.schemas` | `config` |
   | `projects`, `decisions` | `project` |
   | `memory`, `memory-archive` | `memory` |
   | anything else | `content` (fallback) |

   Multiple tags appear if multiple folder types changed.
5. **Stages** everything with `git add -A` (which respects the vault's
   `.gitignore`) and commits.

### Commit message format

```
Vault update: 3 new, 1 modified [research, session-log]

  research/transformers.md
  research/rag-eval.md
  daily/2026-06-02.md
  … and 1 more

Indexed-at: 2026-06-02T02:00:11Z
```

- **Summary line:** `Vault update: <counts> [<tags>]` — counts list only
  non-empty buckets (`N new, N modified, N deleted`).
- **Detail block:** first 8 changed paths (two-space indented); `… and N more`
  if there are more.
- **Footer:** `Indexed-at: <UTC ISO timestamp>`.

### Flags & output

| Flag | Effect |
|---|---|
| *(none)* | Stage + commit; print `Committed N change(s) [<hash>]`. |
| `--dry-run` | Show what *would* be committed (and the message); commit nothing. |
| `--json` | Emit machine-readable stats. |

`--json` shapes:

```jsonc
// clean
{"status":"clean","new":0,"modified":0,"deleted":0,"committed":false,"message":null}
// dry-run
{"status":"dry-run","new":3,"modified":1,"deleted":0,"committed":false,
 "message":"…","files":{"new":[…],"modified":[…],"deleted":[…]}}
// committed
{"status":"committed","new":3,"modified":1,"deleted":0,"committed":true,
 "commit":"a1b2c3d","message":"…"}
```

**Exit codes:** `0` clean / dry-run / successful commit; `1` if `VAULT_PATH`
unset or `git commit` failed.

---

## `atlas changelog` — what changed over a window

### How it works

Read-only. Runs a single:

```
git log --since=<window> --format=%H|%ai|%s --name-status --diff-filter=ADM \
  -- *.md scripts/*.py .schemas/* *.json *.yaml *.yml
```

- `--diff-filter=ADM` limits to Added / Modified / Deleted.
- The pathspec keeps it to notes, scripts, schemas, and config files.
- Each commit is parsed into a `CommitEntry` (8-char hash, `YYYY-MM-DD HH:MM:SS`
  date, subject, and per-category file lists).

**Aggregation** unions files across all commits in the window, with dedup
precedence: a deleted file overrides added/modified; an added file overrides
modified. So the lists are the *net* set of files touched.

### The window

`--since` accepts **any git date expression** and defaults to **`"24 hours ago"`**:

```bash
atlas changelog                          # last 24h
atlas changelog --since "7 days ago"
atlas changelog --since 2026-06-01
```

### Output modes

Default is plain text. `--markdown` for briefings/email, `--json` for the
dashboard (JSON wins if both are given).

```jsonc
// --json
{
  "since": "24 hours ago",
  "commits": 4,
  "added":    ["research/rag.md", …],
  "modified": ["wiki/index.md", …],
  "deleted":  [],
  "commit_list": [{"hash":"a1b2c3d4","date":"2026-06-02 02:00:11","subject":"Vault update: …"}]
}
```

`--markdown` produces `## Vault changelog since <window>`, a totals line, an
`### Added/Modified/Deleted (N)` section each (paths in backticks), and an
`### Commits` list. Plain text uses `+ / ~ / -` prefixes for added/modified/deleted.

**Exit code:** `1` only if `VAULT_PATH` is unset.

---

## How they're used together

The `nightly-obsidian-index` skill runs the index, then `atlas commit` to record
the night's changes, and the morning report uses `atlas changelog --markdown` to
tell you what changed overnight. See
[skills-and-automation.md](skills-and-automation.md).

```bash
# nightly, roughly:
atlas embed --incremental
atlas commit
atlas changelog --since "24 hours ago" --markdown
```

## Configuration

Only `VAULT_PATH` (a git repo). To start one:

```bash
cd "$VAULT_PATH" && git init && git add -A && git commit -m "Initialise vault"
```

> Keep the vault repo **private and separate** from the public Atlas OS repo, and
> give it its own `.gitignore` for anything sensitive.

See also: [`docs/SCRIPTS.md`](../SCRIPTS.md#vault_commitpy) ·
[knowledge-vault.md](knowledge-vault.md)
