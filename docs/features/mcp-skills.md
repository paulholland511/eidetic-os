# Feature: MCP skills

**Source:** [`eidetic_os/mcp_server.py`](../../eidetic_os/mcp_server.py),
[`mcp_client.py`](../../eidetic_os/mcp_client.py),
[`mcp_skill.py`](../../eidetic_os/mcp_skill.py) ·
**CLI:** `eidetic mcp serve`, `eidetic mcp list-tools`, `eidetic skills run <name>`

Eidetic OS speaks the **Model Context Protocol (MCP)** — the interoperability
standard for tool/skill exchange across Claude Code, Cowork, and third-party
clients. This works in both directions:

- **Eidetic OS as an MCP server.** `eidetic mcp serve` exposes the core Eidetic
  capabilities (RAG search, embedding, doctor, the skills catalog, the audit
  trail) as MCP tools, so any MCP host can drive Eidetic OS directly.
- **Skills as MCP servers.** Every `SKILL.md` skill is exposed as an MCP tool —
  **unmodified**. `eidetic skills run <name>` serves one skill over stdio; an MCP
  host calls the tool and gets back the skill's ready-to-run instructions.
- **Eidetic OS as an MCP client.** The runtime can launch/connect to any MCP server
  — local (stdio subprocess) or remote (HTTP/SSE) — perform the handshake, list
  its tools, and call them.

The whole layer is **dependency-free**: JSON-RPC 2.0 over the standard library
(`subprocess` for stdio) plus `requests` (already a core dependency) for HTTP.
No async, no third-party SDK — which keeps the base install slim.

---

## Why MCP

Eidetic skills were an internal registry with a bespoke `SKILL.md` format and a
custom runner. MCP has become the lingua franca for tools and skills. Speaking it
natively means an Eidetic skill is usable from *any* MCP host, and Eidetic can consume
*any* MCP server as a skill — without a translation layer per integration.

```
┌────────────────────┐        MCP         ┌─────────────────────┐
│  eidetic_os runtime  │◄──────stdio───────►│  skill MCP server   │
│   (MCP client)     │      SSE / HTTP    │  (tools + schemas)  │
└────────────────────┘                    └─────────────────────┘
        ▲
        │ also a server-of-servers: `eidetic mcp serve` exposes
        │ Eidetic capabilities to Claude Code / Cowork / any host
```

---

## Eidetic OS as an MCP server

```bash
eidetic mcp list-tools        # see what's exposed
eidetic mcp serve             # start the server (stdio; blocks until EOF)
```

The server exposes five tools, each backed by the same code path as the
equivalent `eidetic` command, so the MCP surface never drifts from the CLI:

| Tool | Arguments | Returns |
|---|---|---|
| `search` | `query`* , `top_k`, `mode`, `folders[]`, `tags[]` | Top RAG hits as JSON. |
| `embed` | `mode` (`full` / `incremental`) | The embed run's output. |
| `doctor` | — | The health report as JSON. |
| `skills_list` | — | The agent-skills catalog as JSON. |
| `audit_query` | `since`, `action`, `limit` | Audit-trail entries as JSON. |

(`*` = required.)

To register Eidetic OS with an MCP host, point it at the launch command:

```json
{
  "mcpServers": {
    "eidetic-os": { "command": "eidetic", "args": ["mcp", "serve"] }
  }
}
```

---

## Skills as MCP servers

Every bundled skill is exposed as an MCP tool with **no changes to the skill** —
the tool surface is derived from the existing `SKILL.md` frontmatter, so anything
that already ships works through the MCP layer (the backwards-compatibility
guarantee).

```bash
eidetic skills run daily-trading-report
```

This launches a one-skill MCP server over stdio. Calling its tool renders the
skill's `SKILL.md` — `{{PLACEHOLDER}}` tokens filled from the environment — and
returns the instructions. A host can override tokens per call:

```jsonc
// tools/call arguments
{ "placeholders": { "VAULT_PATH": "/path/to/vault" } }
```

Under the hood, [`mcp_skill.py`](../../eidetic_os/mcp_skill.py) does the projection:

- `skill_to_tool(skill)` → one MCP `Tool` whose handler renders the `SKILL.md`.
- `build_skill_server(slugs=None)` → an `MCPServer` exposing every skill (or a
  chosen subset).

---

## Eidetic OS as an MCP client

[`mcp_client.py`](../../eidetic_os/mcp_client.py) is a synchronous client over a
`Transport` abstraction:

- `StdioTransport([...command...])` — launches an MCP server as a subprocess and
  frames messages as newline-delimited JSON on its stdin/stdout.
- `HttpTransport(url)` — POSTs JSON-RPC and accepts either an `application/json`
  or a `text/event-stream` (SSE) reply.

```python
import sys
from eidetic_os.mcp_client import MCPClient, StdioTransport

with MCPClient(StdioTransport([sys.executable, "-m", "eidetic_os", "mcp", "serve"])) as client:
    client.initialize()                      # handshake + notifications/initialized
    for tool in client.list_tools():         # tools/list
        print(tool.name, "—", tool.description)
    result = client.call_tool("search", {"query": "kelly criterion"})  # tools/call
    print(result.text)
```

A tool that fails returns a result with `is_error=True` (the MCP convention);
a protocol-level problem (unknown method, malformed request) raises
`MCPClientError`.

---

## MCP-server skills in the marketplace

A skill can declare itself an MCP server (rather than a plain prompt skill) by
adding an `mcp_server` block to its `SKILL.md` frontmatter:

```yaml
---
name: team-search
description: Shared team search served from a central MCP server.
mcp_server:
  transport: http          # stdio | http | sse
  url: https://team.internal/mcp
---
```

…or, for a local subprocess server:

```yaml
mcp_server:
  transport: stdio
  command: ["eidetic", "skills", "run", "team-search"]
```

The block's shape is validated at publish time (`eidetic skills publish`), and
`eidetic skills install` detects it and reports the transport. The runtime turns a
block into a live transport with `transport_from_manifest(config)`.

---

## Protocol notes

- **Transport framing.** stdio uses MCP's newline-delimited JSON (one message per
  line). HTTP accepts JSON or SSE responses.
- **Handshake.** `initialize` → server advertises `protocolVersion`,
  `capabilities`, and `serverInfo`; the client follows with a
  `notifications/initialized` notification. The protocol version is echoed back
  tolerantly (defaulting to `2024-11-05`).
- **Validation.** The server lightweight-validates `tools/call` arguments against
  each tool's `inputSchema` (required keys and top-level types) before the handler
  runs — bad calls come back as tool errors, not crashes.

---

## See also

- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — component 13, the MCP layer.
- [`docs/features/skills-and-automation.md`](skills-and-automation.md) — the
  `SKILL.md` format and the skills catalog.
- [`docs/features/skills-marketplace.md`](skills-marketplace.md) — registries,
  publishing, and the manifest schema.
- [`docs/CLI-REFERENCE.md`](../CLI-REFERENCE.md) — `eidetic mcp` and `eidetic skills
  run` reference.
