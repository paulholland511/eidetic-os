# FAQ & Troubleshooting

Common questions and fixes. For full setup see [`SETUP.md`](SETUP.md); for
config see [`CONFIGURATION.md`](CONFIGURATION.md).

## General

**Do I need Obsidian?**
No. The vault is just a folder of `.md` files. Obsidian is a nice editor and the
frontmatter/wikilink conventions match it, but everything works with any editor.

**Do I need a Claude Cowork subscription?**
Only for the *scheduled tasks* (the `skills/`) and memory features. The Python
scripts — RAG, graph, git, email, health, schemas — run standalone with just
Python.

**Does any of my data leave my machine?**
Not by default. Embeddings and chat go to the endpoint *you* configure
(`localhost`/LAN with a local LLM). Email goes through *your* SMTP account. The
only opt-in external call is the trading cloud Portfolio Manager, off by
default. See [`DATA-CLASSIFICATION.md`](DATA-CLASSIFICATION.md).

**Can I run it without a local LLM?**
Yes — the vault, frontmatter schemas, git automation, changelog, email, and
health check all work without one. Only RAG search and the trading module need
an LLM endpoint.

## Setup & configuration

**`VAULT_PATH environment variable is not set` / scripts use the wrong folder.**
You didn't load your `.env` into the shell. Run `set -a; source .env; set +a`
in the same session before running scripts. Env vars don't persist across
terminals — re-source per session, or use [`direnv`](https://direnv.net/).

**Which chat-endpoint variable do I set, `LM_STUDIO_URL` or `LM_STUDIO_ENDPOINT`?**
Both exist for historical reasons and have different shapes.
`scripts/trading_briefing.py` reads `LM_STUDIO_URL` (**include `/v1`**);
`trading/config.py` + `trading/core.py` read `LM_STUDIO_ENDPOINT` (**no
`/v1`**). For a standard LM Studio / Ollama setup you can leave both unset and
they fall back to `LM_STUDIO_HOST`/`LM_STUDIO_PORT`. See
[`CONFIGURATION.md`](CONFIGURATION.md#local-llm--chat-completions-trading).

## RAG / embeddings

**`Embeddings unreachable` or connection refused.**
Confirm the LLM server is running and the host/port are right:
```bash
curl http://$EMBED_HOST:$EMBED_PORT/v1/models
```
If your endpoint uses a non-standard path, set `EMBED_URL` to the full URL. If
it requires auth, set `EMBED_API_KEY`.

**The first embed run is slow / I want to test before committing to a full run.**
Use `python3 scripts/embed_vault.py --test 5` to embed just 5 files and confirm
the pipeline works, then `--full`.

**A full re-embed got interrupted — do I start over?**
No. `--full` checkpoints progress (`--checkpoint-interval N` tunes how often);
re-running resumes. For day-to-day updates use `--incremental`, which only
embeds files changed since the last run.

**Search results feel stale.**
Run `python3 scripts/embed_vault.py --incremental` (or `--full` weekly). The
nightly/weekly scheduled tasks automate this.

## Git automation

**`vault_commit.py` does nothing / errors about git.**
The vault must be its own git repo. Initialise it:
```bash
cd "$VAULT_PATH" && git init && git add -A && git commit -m "Initialise vault"
```
Keep this repo **separate and private** — it is not the public Atlas OS repo.

**Will it commit secrets from my vault?**
It respects your vault's `.gitignore`. Add a `.gitignore` inside the vault for
anything sensitive. The public Atlas OS `.gitignore` does not cover your private
vault repo.

## Email

**Gmail rejects my password.**
Use an [app password](https://myaccount.google.com/apppasswords) (requires 2FA),
not your account password. Set it as `SMTP_APP_PASSWORD`, and set `SENDER_EMAIL`.

**Email silently doesn't send from a scheduled task.**
The task's environment must have `SMTP_APP_PASSWORD` and `SENDER_EMAIL`. Never
inline credentials in a `SKILL.md`. Run `python3 scripts/health_check.py` —
it reports whether SMTP is configured.

## Scheduled tasks

**How do I install a skill?**
Copy its `skills/<name>/` folder into your Claude scheduled-tasks directory
(`SCHEDULED_DIR`), replace every `{{PLACEHOLDER}}` with your real value, and
register it on the cadence in [`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md).

**Which tasks should I enable first?**
Start with `nightly-obsidian-index`, `nightly-rag-incremental`, and
`weekly-system-health-check`. Add the job-tracker, trading, and newsletter tasks
only if those workflows apply to you.

## Health check

**A subsystem shows DEGRADED.**
That's expected for components you haven't installed (TTS, dashboard). DOWN
means a configured service isn't responding — check that it's running and the
host/port env vars match.

## Still stuck?

- Re-read [`SETUP.md`](SETUP.md) step by step.
- Run `python3 scripts/health_check.py` for a subsystem-by-subsystem status.
- For a clean rebuild, follow [`REBUILD.md`](REBUILD.md).
- Security questions: [`../SECURITY.md`](../SECURITY.md).
