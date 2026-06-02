```
       _   _   _              ___  ____
      / \ | |_| | __ _ ___   / _ \/ ___|
     / _ \| __| |/ _` / __| | | | \___ \
    / ___ \ |_| | (_| \__ \ | |_| |___) |
   /_/   \_\__|_|\__,_|___/  \___/|____/

   A personal AI operating system, built on Claude Cowork.
```

# Atlas OS

**Atlas OS** turns [Claude Cowork](https://claude.ai/) into a personal,
local-first operating system over a markdown knowledge vault. It gives you a
searchable second brain, scheduled automations, automatic git history, and a
set of report/agent workflows — all configured through environment variables and
runnable entirely on your own machine.

It ships with **no personal data, no credentials, and no PII**. Everything is a
template you point at your own vault, your own local LLM, and your own email
account.

> **Privacy by default.** Your notes and embeddings never leave your machine
> unless *you* explicitly wire up an external endpoint. See
> [`SECURITY.md`](SECURITY.md) and [`docs/DATA-CLASSIFICATION.md`](docs/DATA-CLASSIFICATION.md).

## Features

Eight composable systems:

1. **Knowledge vault** — a folder of markdown notes (Obsidian-friendly), with
   per-folder frontmatter schemas kept consistent automatically.
2. **Local RAG search** — chunk + embed your notes via a local LLM into a
   hybrid (vector + keyword) search index.
3. **Knowledge graph** — a wikilink graph derived from your notes for
   backlinks and "related notes".
4. **Git automation** — auto-commit the vault with categorised messages and
   generate changelogs for a morning briefing.
5. **Scheduled tasks** — nightly indexing, daily reports, weekly health checks,
   and more, as Claude Cowork skills.
6. **Email reports** — credential-free SMTP sender for status reports and
   newsletters.
7. **Trading research SDK** *(optional)* — a multi-agent market-research
   framework that writes briefings into your vault. *Not financial advice.*
8. **Voice / TTS hooks & dashboard** *(optional)* — health-check probes for a
   local TTS service, plus a static operations dashboard.

## Quick start

```bash
git clone https://github.com/<your-username>/atlas-os.git ~/code/atlas-os
cd ~/code/atlas-os

python3 -m venv .venv && source .venv/bin/activate
pip install requests pyyaml pdfplumber

cp .env.example .env          # then edit — at minimum set VAULT_PATH
set -a; source .env; set +a

python3 scripts/health_check.py        # see what's up
python3 scripts/embed_vault.py --full  # build the RAG index (needs a local LLM)
```

Full walkthrough: [`docs/SETUP.md`](docs/SETUP.md).

## Prerequisites

- **Claude Cowork** subscription (skills, scheduled tasks, memory)
- **Python 3.11+**
- A **markdown vault** (Obsidian optional)
- *(Optional)* a **local LLM** with an OpenAI-compatible API (LM Studio, Ollama)
  for RAG and the trading module
- *(Optional)* **Node.js** if you build the full dashboard

## Architecture

```
 Claude Cowork ──▶ skills/ (scheduled tasks)
        │
        ├─▶ scripts/  embed · graph · commit · changelog · email · health · trade
        │       │
        │       ├─▶ Markdown vault  (git-tracked, local)
        │       └─▶ .rag/  vectors.json + graph.json  (local, git-ignored)
        │
        └─▶ Local LLM  (embeddings + chat, OpenAI-compatible)
```

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

```
atlas-os/
├── scripts/      RAG, graph, git, email, health-check, trading briefing
├── skills/       9 scheduled-task SKILL.md prompts (templated)
├── schemas/      frontmatter schema enforcement + docs
├── templates/    CLAUDE.md, memory structure, vault skeleton, ops dashboard
├── trading/      optional multi-agent research SDK
├── dashboard/    static ops dashboard + setup notes
└── docs/         architecture, setup, rebuild, data classification, scheduled tasks
```

## Screenshots / demo

_Placeholder — add your own screenshots here once you've set it up._
A static dashboard template lives at
[`templates/ops-dashboard.html`](templates/ops-dashboard.html) (open it in a
browser).

## Configuration

All configuration is via environment variables — see
[`.env.example`](.env.example). Nothing personal is hardcoded anywhere in the
repo.

## Contributing

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md). The golden
rule: **never commit personal data, credentials, or PII.**

## Security

See [`SECURITY.md`](SECURITY.md) for the data-handling policy, credential
management, and responsible-disclosure process.

## License

[MIT](LICENSE).
