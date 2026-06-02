# Data Classification

Atlas OS is designed so that **your data stays on your machine**. This document
classifies the data the system touches and states, for each class, where it
lives and whether it ever leaves the device. It underpins the ISO 27001
alignment claims in [`../SECURITY.md`](../SECURITY.md).

## Classes

| Class | Examples | Storage | Leaves device? |
|---|---|---|---|
| **Public** | This repo's code, docs, templates | The git repo | Yes — it's public by design (and contains no personal data) |
| **Internal** | Your vault notes, RAG vectors, knowledge graph, index files | Local disk (`VAULT_PATH`, `.rag/`) | **No** — never committed here, never transmitted |
| **Confidential** | Job-tracker spreadsheet, trading positions, email content, briefings | Local disk, outside the repo | **No** — explicitly git-ignored; never bundled |
| **Secret** | SMTP app password, API keys | Environment variables only | **No** — never written to the repo or notes |

## Where data flows

- **Embeddings & chat** go to the endpoint you configure. With a *local* LLM
  (the default and recommendation) this is `localhost` or a machine on your LAN —
  nothing leaves your network.
- **The optional cloud Portfolio Manager** (`trading/`) is the only component
  that can call an external API, and only if you set `ANTHROPIC_API_KEY` and
  choose `provider: claude`. It sends only anonymous analyst votes, never your
  notes or positions. It is off by default (`provider: local`).
- **Email** is sent via your own SMTP account to recipients you specify.
- **Web search** (in some scheduled tasks, e.g. the newsletter) queries the
  public web for news — it does not send your data anywhere.

## What is git-ignored (never committed)

The repo's `.gitignore` blocks, among others: `.env`, `*.key`, `*.pem`,
`credentials*`, `*password*`, `*.xlsx`, `vault-content/`, `personal/`,
`job-search/`, `*.sqlite`, `vectors.json`, `graph.json`. See the file for the
full list.

## Your responsibilities

- Keep your **vault in its own private repo** (or no repo) — not inside this one.
- Keep secrets in environment variables; never paste them into notes or code.
- If you build a dashboard, bind it to `localhost` and don't expose it publicly.
- Before sharing any export, scan it for the data classes above.
