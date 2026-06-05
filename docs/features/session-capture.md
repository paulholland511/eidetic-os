# Feature: Session Capture

**Source:** [`scripts/save_sessions.py`](../../scripts/save_sessions.py) ·
**CLI:** `eidetic session save`, `eidetic session list`

This is the feature that gives Eidetic OS a memory. Stock Claude forgets everything
between sessions — close the tab and the research, the planning, the reasoning
behind a decision are gone. Session capture fixes that by folding every Cowork
conversation back into your vault as a clean, searchable markdown note. **Nothing
you discuss with Claude is ever lost**, and because the notes live in the vault,
the RAG pipeline indexes them automatically — your conversations become
retrievable by meaning alongside the rest of your knowledge.

Everything is derived **deterministically from the local transcript — no LLM
call, no network**. The note lives in your own private vault; the script ships no
session content of its own.

---

## How it works

1. **Locates the Cowork session store.** Each Cowork session is a metadata file
   (`local_<id>.json`) plus a sibling workspace holding the conversation in the
   standard Claude Code JSONL format. On macOS the store defaults to
   `~/Library/Application Support/Claude/local-agent-mode-sessions`; override it
   with `CLAUDE_SESSIONS_DIR` or `--sessions-dir PATH`.
2. **Selects the window.** A plain `eidetic session save` processes only sessions
   new or changed since the last run (see the watermark below). `--since 24h`
   (or `7d`, or an ISO date) captures a fixed window; `--all` captures every
   session ever recorded.
3. **Extracts deterministically.** For each selected session it parses the
   transcript locally to derive a summary, the key actions taken, the tool-call
   count, the duration, and — from `Write` / `Edit` / `MultiEdit` /
   `NotebookEdit` calls — the list of files modified.
4. **Writes one note per session** under `$VAULT_PATH/sessions/`, keyed by
   session id and overwritten in place, so re-running is **idempotent**.

### The note format

Each session becomes `sessions/session-log-YYYY-MM-DD-<slug>.md`:

```markdown
---
title: "Session: Refactor the embed checkpointing"
date: 2026-06-02
tags: [session-log, cowork]
session_id: local_a1b2c3
---

# Refactor the embed checkpointing

**Date:** 2026-06-02 14:11
**Duration:** 38m
**Tasks completed:** 7
**Model:** claude-opus-4-8

## Summary
The session opened with: "Can we make the embed resume after a crash?" It ran
for 38m across 42 message(s), using 19 tool call(s).

## Key Actions
- …

## Files Modified
- `scripts/embed_vault.py`
- `tests/test_embed.py`
```

The `tags: [session-log, cowork]` frontmatter is what lets the RAG indexer and
any agent searching the vault recognise these as captured conversations.

### The watermark

A watermark in `$VAULT_PATH/.eidetic/last_session_save.txt` records the latest
`lastActivityAt` timestamp captured so far. A plain `save` only processes
sessions newer than the watermark, and the watermark never moves backwards — so
repeated and overlapping runs never double-write a session. This is what makes
the twice-daily schedule (two 12-hour windows) safe.

---

## Flags & output

| Command / flag | Effect |
|---|---|
| `eidetic session save` | Capture new/changed sessions since the last run. |
| `--since 24h \| 7d \| 2026-06-01` | Capture sessions active in a fixed window. |
| `--all` | Capture every session ever recorded. |
| `eidetic session list` (`--list`) | List recent sessions; write nothing. |
| `--limit N` | Max sessions shown for `list` (default 20). |
| `--sessions-dir PATH` | Read from a custom Cowork store. |
| `--json` | Machine-readable summary (for scheduled tasks / the audit trail). |

```bash
eidetic session list          # what's available
eidetic session save --all    # backfill everything once
eidetic session save          # thereafter: only what's new
```

Like every script-wrapping command, `eidetic session` appends an entry to the
[audit trail](../../README.md#audit-trail) when it finishes.

---

## Automation — capture, twice daily

The recommended default is **twice daily**: a morning and an afternoon pass, each
covering a 12-hour window, so work lands in the vault close to when it happened.

```bash
eidetic skills install morning-session-capture     # ~09:00, --since 12h
eidetic skills install afternoon-session-capture   # ~17:00, --since 12h
```

Both run `EIDETIC_TRIGGER=scheduled eidetic session save --since 12h`; the shared
watermark means the overlapping windows never double-write. Prefer one nightly
run? Install `daily-session-capture` (`--since 24h`). Record your cadence in
`.env`:

```bash
SESSION_CAPTURE_FREQUENCY=twice    # twice (default) | daily | hourly | manual
```

The pair also ships in the [`knowledge` pack](../SCHEDULED-TASKS.md):
`eidetic skills install-pack knowledge` sets up session capture alongside the
nightly index and RAG embed.

---

## Why it matters

Session capture is what turns the vault from a notes folder into the
institutional memory of your AI-assisted work:

- **Conversations are preserved.** Research sessions, code reviews, debugging
  threads, planning discussions — all become permanent, searchable notes.
- **Research is captured the same way.** The deep-research skills
  (`deep-research`, `autoresearch`, `topic-research-brief`) write their findings
  into the vault as notes, so the same nightly embed folds them into the **same
  knowledge graph** as your chats.
- **The vault gets smarter over time.** Every captured session and embedded
  research brief adds context, sharpening what Claude can retrieve and reason
  over next time.

See also: [knowledge-vault.md](knowledge-vault.md) ·
[rag-search.md](rag-search.md) ·
[skills-and-automation.md](skills-and-automation.md) ·
[`docs/SCHEDULED-TASKS.md`](../SCHEDULED-TASKS.md)
