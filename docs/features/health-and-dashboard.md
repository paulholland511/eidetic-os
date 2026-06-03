# Feature: Health Check & Dashboard

**Source:** [`scripts/health_check.py`](../../scripts/health_check.py),
[`templates/ops-dashboard.html`](../../templates/ops-dashboard.html) ·
**CLI:** `atlas health`, `atlas doctor`

Atlas OS can probe every subsystem and report its status — on the command line,
as JSON for a dashboard, or as part of the weekly health-check skill.

---

## Health check (`atlas health`)

### How it works

`health_check.py` runs **endpoint-aware** probes: each HTTP service has a
known-good URL and an *accept range*, so a backend that returns 404 on `/` by
design isn't falsely marked down. It checks nine subsystems:

| Subsystem | Probe |
|---|---|
| **Vault** | counts `*.md`; freshness of `.claude-index.md`, `wiki/index.md`, `wiki/hot.md`, `wiki/log.md` (≤14 days) |
| **RAG Pipeline** | `vectors.db` exists (+ size; legacy `vectors.json` accepted); `last_embed.txt` ≤7 days; `GET $EMBED_HOST:$EMBED_PORT/v1/models` |
| **TTS** | `GET $TTS_HOST:$TTS_PORT/` (accept 200–499) |
| **Email** | `send_email.py` present + `SMTP_APP_PASSWORD` set |
| **Git** | no stale `.git/index.lock`; `git status` clean-ish; last commit readable |
| **Scheduled Tasks** | `SCHEDULED_DIR` exists; ≥1 subdir with a `SKILL.md` |
| **Dashboard** | frontend port, backend root (accept 200–499), and `/api/health` (accept **200–299** only) |
| **Schemas** | `.schemas` dir + `enforce_schemas.py` present |
| **Wiki** | `wiki/` exists; index/hot/log fresh (≤14 days) |

**Status logic** (`combine`): a subsystem is **`up`** if all its checks pass,
**`down`** if none pass, **`degraded`** if some pass. Icons: ✅ / ⚠️ / ❌.

> A subsystem you intentionally haven't installed (TTS, dashboard) shows
> **degraded** — that's expected, not a failure.

### Usage & output

```bash
atlas health            # human-readable report
atlas health --json     # machine-readable (powers the dashboard)
atlas health --quiet    # no output; exit code only
```

`--json` emits a **top-level array**, one object per subsystem:

```json
[
  {
    "name": "RAG Pipeline",
    "status": "up",
    "detail": "3/3 checks passed",
    "checks": [
      {"name": "vectors.db", "ok": true, "detail": "12.4 MB"},
      {"name": "last_embed.txt", "ok": true, "detail": "age 7.0h (limit 168h)"},
      {"name": "embeddings endpoint", "ok": true, "detail": "HTTP 200"}
    ]
  }
]
```

**Exit code:** `0` if nothing is `down` (degraded still passes); `1` if any
subsystem is `down`.

### `atlas doctor` vs `atlas health`

- **`atlas doctor`** — a quick *setup* validation (Python version, vault exists +
  git, RAG index present, embeddings reachable, SMTP configured). Use it right
  after `atlas init`.
- **`atlas health`** — the full nine-subsystem probe above. Use it for ongoing
  monitoring and the dashboard.

---

## Dashboard

Atlas OS ships a self-contained, single-file dashboard at
[`templates/ops-dashboard.html`](../../templates/ops-dashboard.html) — **no
bundled data, no `node_modules`**. Open it in a browser as-is, or wire its
`fetch()` calls to a tiny local backend.

It expects two optional JSON endpoints (a ~30-line Flask/Express shim is enough):

| Endpoint | Produced by |
|---|---|
| `GET /api/health` | `atlas health --json` |
| `GET /api/changelog` | `atlas changelog --json` |

A richer graph view can also consume `atlas graph`'s `graph.json` as
`GET /api/graph`.

**Want a full multi-panel app?** Build it as a **separate repository** pointed at
the same local endpoints — keep its dependencies and any cached data out of the
public Atlas OS repo, and have its backend shell out to the Atlas OS commands so
there's a single source of truth for paths/hosts. See
[`dashboard/README.md`](../../dashboard/README.md).

**Privacy:** whichever option you choose, bind the dashboard to `localhost` and
never deploy it publicly with your vault data behind it.

---

## Configuration

| Variable | Default | Used for |
|---|---|---|
| `VAULT_PATH` | `.` | vault/wiki/git/schemas checks |
| `RAG_DIR` | `$VAULT_PATH/.rag` | RAG store freshness |
| `SCHEDULED_DIR` | `~/Documents/Claude/Scheduled` | scheduled-tasks check |
| `EMBED_HOST` / `EMBED_PORT` | `localhost` / `5555` | embeddings probe |
| `TTS_HOST` / `TTS_PORT` | `localhost` / `8800` | TTS probe |
| `DASHBOARD_FRONTEND_PORT` / `DASHBOARD_BACKEND_PORT` | `3000` / `5001` | dashboard probe |
| `SMTP_APP_PASSWORD` | — | email-readiness check |

See also: [git-automation.md](git-automation.md) (`atlas changelog --json`) ·
[knowledge-graph.md](knowledge-graph.md) · [`docs/SCRIPTS.md`](../SCRIPTS.md#health_checkpy)
