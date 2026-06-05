# Eidetic OS — Dashboard

Eidetic OS does not bundle a heavyweight dashboard application (it would carry
personal data and a large `node_modules` tree). Instead you have two options:

## Option 1 — Static template (included)

[`../templates/ops-dashboard.html`](../templates/ops-dashboard.html) is a
self-contained, single-file HTML dashboard with **no bundled data**. Open it in
a browser as-is, or wire its `fetch()` calls to your own local backend.

It expects two optional JSON endpoints:

| Endpoint | Produced by |
|---|---|
| `GET /api/health` | `scripts/health_check.py --json` |
| `GET /api/changelog` | `scripts/vault_changelog.py --json` |

The simplest backend is a tiny script that runs those two scripts on request and
returns their JSON. A ~30-line Flask/Express shim is enough.

## Option 2 — Full dashboard suite

If you want the full multi-panel monitoring app (project management, analytics,
system health, knowledge graph, workflow, etc.), build it as a separate project
and point it at the same local endpoints. Keep it in its **own repository** so
its dependencies and any cached data never end up in this public repo.

Recommended shape:

```
your-dashboard/           # separate repo, NOT committed here
├── server/               # Express/Flask — exposes /api/health, /api/changelog, /api/graph
└── web/                  # React/Svelte frontend
```

Have the backend shell out to the Eidetic OS scripts (which read everything from
env vars) so there is a single source of truth for paths and hosts.

## Privacy

Whichever option you choose, the dashboard must **read from your local machine
only**. Do not deploy it to a public host with your vault data behind it, and
never commit generated data files (`vectors.json`, `graph.json`, exported
boards). See [`../SECURITY.md`](../SECURITY.md).
