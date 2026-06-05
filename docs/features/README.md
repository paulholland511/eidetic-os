# Feature Deep-Dives

One document per feature, explaining **how it actually works** — the internals,
data formats, configuration, and edge cases — grounded in the source code. For
setup and the command reference, see [`docs/SETUP.md`](../SETUP.md) and
[`docs/SCRIPTS.md`](../SCRIPTS.md).

| Feature | Doc | Source | CLI |
|---|---|---|---|
| Knowledge vault & frontmatter schemas | [knowledge-vault.md](knowledge-vault.md) | `schemas/`, `templates/` | `eidetic schemas`, `eidetic init` |
| Session capture | [session-capture.md](session-capture.md) | `scripts/save_sessions.py` | `eidetic session` |
| Local RAG search | [rag-search.md](rag-search.md) | `scripts/embed_vault.py` | `eidetic embed` |
| Pluggable vector backends | [vector-backends.md](vector-backends.md) | `eidetic_os/vector_backend.py`, `eidetic_os/vector_backends/` | `eidetic migrate-vectors --to` |
| Knowledge graph | [knowledge-graph.md](knowledge-graph.md) | `scripts/build_graph.py` | `eidetic graph` |
| Git automation | [git-automation.md](git-automation.md) | `scripts/vault_commit.py`, `vault_changelog.py` | `eidetic commit`, `eidetic changelog` |
| Git sync hardening (safe merge, validation, locking) | [git-hardening.md](git-hardening.md) | `eidetic_os/git_sync.py`, `frontmatter.py`, `filelock.py` | `eidetic sync`, `eidetic validate` |
| Scheduled tasks & skills catalog | [skills-and-automation.md](skills-and-automation.md) | `skills/`, `eidetic_os/_skills.py` | `eidetic skills` |
| Skills marketplace / registry | [skills-marketplace.md](skills-marketplace.md) | `eidetic_os/marketplace.py`, `skills/registry.json` | `eidetic skills search`, `publish`, `registry` |
| MCP skills (Model Context Protocol) | [mcp-skills.md](mcp-skills.md) | `eidetic_os/mcp_server.py`, `mcp_client.py`, `mcp_skill.py` | `eidetic mcp serve`, `eidetic mcp list-tools`, `eidetic skills run` |
| Skill security (scan + sandbox) | [security.md](security.md) | `eidetic_os/security.py`, `eidetic_os/sandbox.py` | `eidetic security scan`, `eidetic security report` |
| Email reports | [email-reports.md](email-reports.md) | `scripts/send_email.py` | `eidetic email` |
| Extension architecture | [extensions.md](extensions.md) | `eidetic_os/extensions/` | `eidetic extensions` |
| Trading research SDK *(optional extension)* | [trading-sdk.md](trading-sdk.md) | `eidetic_os/extensions/trading/`, `scripts/trading_briefing.py` | `eidetic trading` |
| Health check & dashboard | [health-and-dashboard.md](health-and-dashboard.md) | `scripts/health_check.py`, `templates/ops-dashboard.html` | `eidetic health`, `eidetic doctor` |
| Web dashboard | [dashboard.md](dashboard.md) | `eidetic_os/dashboard/` | `eidetic dashboard` |

## How the features fit together

```
          Cowork conversations + research ──(eidetic session save)──┐
                                                                  ▼
              ┌──────────────── the vault (source of truth) ────────────────┐
              │  markdown notes · session logs · frontmatter · [[wikilinks]] │
              └───────┬───────────────┬───────────────┬───────────────┬─────┘
                      │               │               │               │
                 RAG search     knowledge graph   git automation   skills catalog
                (embed → vectors) (links → graph) (commit/changelog) (discoverable)
                      │               │               │               │
                      └───────────────┴───────┬───────┴───────────────┘
                                              │
                              scheduled skills orchestrate them,
                              email reports go out, health check
                              watches it all, the dashboard shows it
```

The vault is the source of truth; RAG, the graph, and git history are derived and
reproducible. **Session capture** feeds it from the other direction — folding your
Cowork conversations and research back into the vault as notes, so they're indexed
and searchable alongside everything else. Scheduled **skills** tie the pieces
together on a cadence; **email** delivers the results; the **health check** and
**dashboard** observe the whole system. The **trading SDK** is an optional
research workload that writes its briefings back into the vault.

See also: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) for the high-level design,
and [`docs/DATA-CLASSIFICATION.md`](../DATA-CLASSIFICATION.md) for what stays
local.
