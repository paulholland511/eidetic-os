# Feature: Scheduled Tasks & the Skills Catalog

**Source:** [`skills/`](../../skills), [`atlas_os/_skills.py`](../../atlas_os/_skills.py) ·
**CLI:** `atlas skills` · **Catalog:** `<vault>/Skills Catalog.md`

This is the "operating system" part of Atlas OS: **autonomous agents that take
action on a schedule**, plus a self-updating catalog so agents can discover what
they can run.

---

## Skills = scheduled Claude Cowork prompts

Each automation is a **skill** — a `SKILL.md` prompt in `skills/<name>/` with
YAML frontmatter (`name`, `description`) followed by the instructions an agent
follows. Claude Cowork runs it on a schedule (or on demand). A skill orchestrates
the Python tooling (`atlas embed`, `atlas commit`, …) and your connected MCP
tools (email, web search, files).

Skills are written to run **unattended** — they make reasonable choices rather
than asking questions. Review a skill before enabling it.

### The shipped skills

| Skill | Suggested cadence | What it does |
|---|---|---|
| `nightly-obsidian-index` | Nightly (~02:00) | Index changed notes, sync the wiki, append the hot cache, commit the vault, write a morning briefing |
| `nightly-rag-incremental` | Nightly (after the index) | Embed only notes changed since the last run |
| `daily-job-tracker-update` | Weekday mornings | Scan email for application updates; update the tracker |
| `afternoon-job-tracker-update` | Weekday ~14:00 | Catch afternoon emails; update the tracker |
| `atlas-daily-report-email` | Daily (~09:30) | Email a status report (job search, health, action items) |
| `daily-trading-report` | Daily (~13:00) | Run analyst agents on a watchlist; email a research report |
| `friday-it-newsletter` | Fridays AM | Compile and email a weekly IT-news digest; save to the vault |
| `weekly-system-health-check` | Weekly | Probe every subsystem; email a health report |
| `weekly-rag-full-reembed` | Weekly (Sun early AM) | Re-embed the entire vault from scratch |

### Installing a skill

Copy `skills/<slug>/` into your Claude scheduled-tasks directory (`SCHEDULED_DIR`),
replace the `{{PLACEHOLDER}}` tokens with your real values, and register it on its
cadence. Placeholder tokens (`{{VAULT_PATH}}`, `{{ATLAS_OS}}`, `{{USER_EMAIL}}`,
`{{EMBED_HOST}}`/`{{LLM_PORT}}`, `{{JOB_TRACKER_PATH}}`, `{{WATCHLIST}}`, …) are
documented in [`docs/SCHEDULED-TASKS.md`](../SCHEDULED-TASKS.md).

> Never inline credentials in a `SKILL.md`. Email-sending skills read
> `SMTP_APP_PASSWORD`/`SENDER_EMAIL` from the environment.

---

## The skills catalog (agent discovery)

Atlas OS generates a **`Skills Catalog.md`** note inside your vault — an
always-current index of every skill — so any agent that reads or searches the
vault can discover the full menu of automations it can invoke.

### How it works

`atlas_os/_skills.py` parses each `skills/*/SKILL.md`'s YAML frontmatter
(`name`, `description`), pairs it with a suggested cadence, and renders a markdown
note:

- It carries `type: reference` frontmatter, so the [RAG indexer](rag-search.md)
  picks it up like any other note (agents can find it via search).
- It's built **from the SKILL.md files themselves**, so it never drifts from the
  actual skills.
- It lands at `<vault>/Skills Catalog.md` (override with `--output`).

### Usage

```bash
atlas skills          # list the catalog in the terminal
atlas skills --sync   # (re)generate Skills Catalog.md in the vault
```

`atlas init` generates it on first setup. **Re-run `atlas skills --sync` whenever
you add, remove, or edit a skill** — it's auto-generated, so don't hand-edit it.

### Adding your own skill

1. Create `skills/<slug>/SKILL.md` with `name` + `description` frontmatter and the
   prompt body.
2. `atlas skills --sync` — it appears in the catalog automatically.
3. Install it into your scheduled-tasks directory and register a cadence.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_PATH` | — (**required** for `--sync`) | where the catalog is written |
| `SCHEDULED_DIR` | `~/Documents/Claude/Scheduled` | where installed skills live (probed by `atlas health`) |
| `USER_EMAIL` | — | recipient for report skills |

See also: [`docs/SCHEDULED-TASKS.md`](../SCHEDULED-TASKS.md) (cadences, placeholder
tokens, safety notes) · [email-reports.md](email-reports.md) ·
[health-and-dashboard.md](health-and-dashboard.md)
