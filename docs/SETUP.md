# Setup

Step-by-step installation of Atlas OS from scratch.

## Prerequisites

- **Claude Cowork** subscription (for skills, scheduled tasks, memory)
- **Python 3.11+** (3.13 recommended)
- **Git**
- A **markdown vault** — a folder of `.md` notes (Obsidian optional but nice)
- *(Optional)* A **local LLM** exposing an OpenAI-compatible API for embeddings
  and chat — e.g. [LM Studio](https://lmstudio.ai/) or
  [Ollama](https://ollama.com/). Without it, RAG and trading features are off,
  but the vault, schemas, git, and reporting still work.
- *(Optional)* **Node.js** if you build the full dashboard.

## 1. Clone

```bash
git clone https://github.com/<your-username>/atlas-os.git ~/code/atlas-os
cd ~/code/atlas-os
```

## 2. Python environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests pyyaml pdfplumber          # core
pip install yfinance                            # only for the trading module
```

## 3. Configure

```bash
cp .env.example .env
$EDITOR .env
```

Set at minimum `VAULT_PATH`. If you have a local LLM, set `EMBED_HOST`/
`EMBED_PORT`/`EMBED_MODEL`. For email reports set `SENDER_EMAIL`,
`USER_EMAIL`, and `SMTP_APP_PASSWORD`.

Load it into your shell (or use a tool like `direnv`):

```bash
set -a; source .env; set +a
```

## 4. Create the vault skeleton

If you're starting a fresh vault, copy the skeleton and drop the `.template`
suffixes:

```bash
mkdir -p "$VAULT_PATH/wiki"
cp templates/vault-skeleton/.claude-index.md.template   "$VAULT_PATH/.claude-index.md"
cp templates/vault-skeleton/wiki/index.md.template      "$VAULT_PATH/wiki/index.md"
cp templates/vault-skeleton/wiki/hot.md.template        "$VAULT_PATH/wiki/hot.md"
cp templates/vault-skeleton/wiki/log.md.template        "$VAULT_PATH/wiki/log.md"
cp "templates/vault-skeleton/Operations Dashboard.md"   "$VAULT_PATH/"
```

Initialise git in the vault so the commit/changelog tasks work:

```bash
cd "$VAULT_PATH" && git init && git add -A && git commit -m "Initialise vault"
cd -
```

> Add a `.gitignore` inside your vault for anything personal you don't want in
> its own history (the public Atlas OS `.gitignore` does not cover your private
> vault repo).

## 5. Frontmatter schemas (optional but recommended)

```bash
python3 schemas/enforce_schemas.py --dry-run     # preview
python3 schemas/enforce_schemas.py               # apply
```

## 6. Build the RAG index (requires a local LLM)

```bash
python3 scripts/embed_vault.py --test 5          # smoke test on 5 files
python3 scripts/embed_vault.py --full            # full index
```

## 7. Install the CLAUDE.md and memory

```bash
cp templates/CLAUDE.md.template ~/CLAUDE.md        # then edit placeholders
# Memory lives wherever your Claude memory directory is:
cp templates/memory-structure/MEMORY.md.template <your-memory-dir>/MEMORY.md
```

## 8. Install the scheduled tasks

Copy each skill folder into your Claude scheduled-tasks directory and replace
the `{{PLACEHOLDER}}` tokens with your real values. See
[`SCHEDULED-TASKS.md`](SCHEDULED-TASKS.md) for suggested cadences and the full
placeholder list.

## 9. Verify

```bash
python3 scripts/health_check.py
```

You should see each subsystem report UP / DEGRADED / DOWN.

## Troubleshooting

- **"VAULT_PATH environment variable is not set"** — you didn't export `.env`.
- **Embeddings unreachable** — confirm your local LLM is running and
  `EMBED_HOST:EMBED_PORT` is correct; `curl http://$EMBED_HOST:$EMBED_PORT/v1/models`.
- **Email fails** — for Gmail you need an app password (2FA required), set as
  `SMTP_APP_PASSWORD`. Regular account passwords won't work.
