"""Atlas OS as a Model Context Protocol (MCP) server.

This module has two layers:

1. **A tiny, dependency-free MCP server core** (:class:`MCPServer`, :class:`Tool`)
   that speaks JSON-RPC 2.0 over a line-delimited stdio transport. It implements
   just enough of the MCP spec for a host (Claude Code, Cowork, any MCP client)
   to ``initialize``, ``tools/list``, and ``tools/call``. The skill wrapper
   (:mod:`atlas_os.mcp_skill`) reuses this same core, so there is exactly one
   protocol implementation in the codebase.

2. **The Atlas OS server itself** (:func:`build_atlas_server`) — it surfaces the
   core Atlas capabilities as MCP tools so an external host can drive Atlas OS
   directly: ``search`` (RAG), ``embed``, ``doctor``, ``skills_list`` and
   ``audit_query``.

The transport is deliberately minimal: one JSON object per line on stdin/stdout,
matching MCP's stdio framing (messages are newline-delimited and must not embed
raw newlines). No async, no third-party SDK — the standard library is enough for
a single-client, request/response server, which keeps the core install slim.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

# The MCP protocol revision we advertise. 2024-11-05 is broadly supported across
# hosts; when a client asks for a different revision we echo its choice back (a
# tolerant handshake), falling back to this when it sends nothing.
PROTOCOL_VERSION = "2024-11-05"

# JSON-RPC 2.0 error codes (the subset we emit).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# A tool handler takes the validated ``arguments`` object and returns the text
# result. Raise to signal a tool-level failure (reported as an ``isError`` result
# block, per MCP — distinct from a protocol-level JSON-RPC error).
ToolHandler = Callable[[Mapping[str, Any]], str]


class MCPError(Exception):
    """A protocol-level error to return as a JSON-RPC ``error`` object."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Tool:
    """One MCP tool: a name, a description, a JSON-Schema input, and a handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def definition(self) -> dict[str, Any]:
        """The ``tools/list`` wire form (name, description, inputSchema)."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def _empty_object_schema() -> dict[str, Any]:
    """A JSON Schema accepting an empty object — the default tool input."""
    return {"type": "object", "properties": {}, "additionalProperties": False}


# ── Lightweight argument validation ───────────────────────────────────────────
# Not a full JSON-Schema validator — just the cases a hand-written tool schema
# uses (required keys, top-level property types). Enough to reject obviously bad
# calls server-side before a handler runs, without pulling in jsonschema.
_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate_arguments(schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> list[str]:
    """Return a list of human-readable problems with ``arguments`` (empty = ok)."""
    problems: list[str] = []
    required = schema.get("required") or []
    if isinstance(required, list):
        for key in required:
            if key not in arguments:
                problems.append(f"missing required argument {key!r}")

    properties = schema.get("properties") or {}
    if isinstance(properties, Mapping):
        for key, value in arguments.items():
            spec = properties.get(key)
            if not isinstance(spec, Mapping):
                continue  # unknown / unconstrained property — allow it
            expected = spec.get("type")
            # `bool` is a subclass of `int`; guard so a boolean isn't accepted as
            # an integer/number argument.
            if expected == "integer" or expected == "number":
                if isinstance(value, bool) or not isinstance(value, _JSON_TYPES[expected]):
                    problems.append(f"argument {key!r} must be a {expected}")
            elif isinstance(expected, str) and expected in _JSON_TYPES:
                if not isinstance(value, _JSON_TYPES[expected]):
                    problems.append(f"argument {key!r} must be a {expected}")
    return problems


@dataclass
class MCPServer:
    """A line-delimited JSON-RPC 2.0 MCP server over stdio.

    Register tools at construction (or with :meth:`add_tool`), then call
    :meth:`serve` to run the read/dispatch/write loop until EOF. The same
    instance can also be driven message-by-message via :meth:`handle_message`,
    which is what the tests exercise without spawning a process.
    """

    name: str
    version: str
    tools: list[Tool] = field(default_factory=list)

    def add_tool(self, tool: Tool) -> None:
        """Register a tool (later registrations override an earlier same name)."""
        self.tools = [t for t in self.tools if t.name != tool.name]
        self.tools.append(tool)

    def _tool(self, name: str) -> Tool | None:
        return next((t for t in self.tools if t.name == name), None)

    # ── Method handlers ───────────────────────────────────────────────────────
    def _initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) and requested else PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self.name, "version": self.version},
        }

    def _list_tools(self, _params: Mapping[str, Any]) -> dict[str, Any]:
        return {"tools": [t.definition() for t in self.tools]}

    def _call_tool(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            raise MCPError(INVALID_PARAMS, "tools/call requires a string 'name'")
        tool = self._tool(name)
        if tool is None:
            raise MCPError(INVALID_PARAMS, f"unknown tool {name!r}")

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, Mapping):
            raise MCPError(INVALID_PARAMS, "'arguments' must be an object")

        problems = validate_arguments(tool.input_schema, arguments)
        if problems:
            return _tool_error("; ".join(problems))

        try:
            text = tool.handler(arguments)
        except Exception as exc:  # noqa: BLE001 - surface as a tool error, not a crash
            return _tool_error(f"{type(exc).__name__}: {exc}")
        return {"content": [{"type": "text", "text": text}], "isError": False}

    # ── Dispatch ──────────────────────────────────────────────────────────────
    def handle_message(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        """Dispatch one JSON-RPC message; return the response, or None for a notification."""
        msg_id = message.get("id")
        method = message.get("method")

        # Notifications (no id) get no response — e.g. notifications/initialized.
        is_notification = "id" not in message
        if not isinstance(method, str):
            if is_notification:
                return None
            return _error_response(msg_id, INVALID_REQUEST, "missing method")

        params = message.get("params") or {}
        if not isinstance(params, Mapping):
            params = {}

        handlers: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
            "initialize": self._initialize,
            "tools/list": self._list_tools,
            "tools/call": self._call_tool,
            "ping": lambda _p: {},
        }

        if method.startswith("notifications/"):
            return None  # acknowledged silently

        handler = handlers.get(method)
        if handler is None:
            if is_notification:
                return None
            return _error_response(msg_id, METHOD_NOT_FOUND, f"unknown method {method!r}")

        try:
            result = handler(params)
        except MCPError as exc:
            return _error_response(msg_id, exc.code, exc.message)

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def serve(self, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None:
        """Run the stdio read/dispatch/write loop until the input stream closes."""
        source = stdin if stdin is not None else sys.stdin
        sink = stdout if stdout is not None else sys.stdout
        for line in source:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                _write_message(sink, _error_response(None, PARSE_ERROR, "invalid JSON"))
                continue
            if not isinstance(message, Mapping):
                _write_message(sink, _error_response(None, INVALID_REQUEST, "not an object"))
                continue
            response = self.handle_message(message)
            if response is not None:
                _write_message(sink, response)


def _tool_error(text: str) -> dict[str, Any]:
    """A ``tools/call`` result flagged as an error (MCP isError convention)."""
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _error_response(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _write_message(sink: IO[str], message: Mapping[str, Any]) -> None:
    sink.write(json.dumps(message, ensure_ascii=False) + "\n")
    sink.flush()


# ──────────────────────────────────────────────────────────────────────────────
# The Atlas OS server — Atlas capabilities exposed as MCP tools.
# ──────────────────────────────────────────────────────────────────────────────
# Each tool shells out to (or calls into) the same code paths the CLI uses, so
# the MCP surface never drifts from `atlas <command>`. Handlers return plain text
# (the tool result block); JSON output is embedded as a fenced/inline string so a
# host gets structured data when it asks for it.
def _scripts_dir() -> Path:
    from atlas_os._paths import scripts_dir

    return scripts_dir()


def _run_script(script: Path, args: Sequence[str]) -> str:
    """Run one of the bundled pipeline scripts and return its combined output."""
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(out.strip() or f"exit code {proc.returncode}")
    return out.strip()


def _tool_search(arguments: Mapping[str, Any]) -> str:
    query = str(arguments["query"])
    top_k = int(arguments.get("top_k", 5))
    mode = str(arguments.get("mode", "hybrid"))
    args = [query, "--top-k", str(top_k), "--mode", mode, "--json"]
    for folder in arguments.get("folders") or []:
        args += ["--folder", str(folder)]
    for tag in arguments.get("tags") or []:
        args += ["--tag", str(tag)]
    return _run_script(_scripts_dir() / "rag_search.py", args)


def _tool_embed(arguments: Mapping[str, Any]) -> str:
    mode = str(arguments.get("mode", "incremental"))
    flag = {"full": "--full", "incremental": "--incremental"}.get(mode, "--incremental")
    return _run_script(_scripts_dir() / "embed_vault.py", [flag])


def _tool_doctor(_arguments: Mapping[str, Any]) -> str:
    from atlas_os.cli import _doctor_results

    results = _doctor_results()
    payload = {
        "checks": [c.as_dict() for c in results],
        "summary": {
            "ok": sum(1 for c in results if c.status == "OK"),
            "warn": sum(1 for c in results if c.status == "WARN"),
            "fail": sum(1 for c in results if c.status == "FAIL"),
        },
    }
    return json.dumps(payload, indent=2)


def _tool_skills_list(_arguments: Mapping[str, Any]) -> str:
    from atlas_os._skills import load_skills

    skills = [
        {"slug": s.slug, "name": s.name, "description": s.description, "cadence": s.cadence}
        for s in load_skills()
    ]
    return json.dumps({"skills": skills, "count": len(skills)}, indent=2)


def _tool_audit_query(arguments: Mapping[str, Any]) -> str:
    from atlas_os import audit

    since = arguments.get("since")
    action = arguments.get("action")
    limit = int(arguments.get("limit", 20))
    entries = audit.read_audit(
        since=str(since) if since else None,
        action=str(action) if action else None,
        limit=limit,
    )
    return json.dumps({"entries": entries, "count": len(entries)}, indent=2)


def build_atlas_server() -> MCPServer:
    """Build the Atlas OS MCP server: search, embed, doctor, skills_list, audit_query."""
    from atlas_os import __version__

    server = MCPServer(name="atlas-os", version=__version__)
    server.add_tool(
        Tool(
            name="search",
            description=(
                "Hybrid (BM25 + vector) RAG search over the Obsidian vault. "
                "Returns the top matching note chunks as JSON."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "top_k": {"type": "integer", "description": "Results to return (default 5)."},
                    "mode": {
                        "type": "string",
                        "description": "hybrid | vector | keyword (default hybrid).",
                    },
                    "folders": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Restrict to these vault folders.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Restrict to chunks carrying these tags.",
                    },
                },
                "required": ["query"],
            },
            handler=_tool_search,
        )
    )
    server.add_tool(
        Tool(
            name="embed",
            description="Build or refresh the RAG vector store from the vault.",
            input_schema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "full | incremental (default incremental).",
                    }
                },
            },
            handler=_tool_embed,
        )
    )
    server.add_tool(
        Tool(
            name="doctor",
            description="Validate the Atlas OS setup; returns a JSON health report.",
            input_schema=_empty_object_schema(),
            handler=_tool_doctor,
        )
    )
    server.add_tool(
        Tool(
            name="skills_list",
            description="List the agent skills shipped with this Atlas OS install (JSON).",
            input_schema=_empty_object_schema(),
            handler=_tool_skills_list,
        )
    )
    server.add_tool(
        Tool(
            name="audit_query",
            description="Query the append-only audit trail of Atlas OS actions (JSON).",
            input_schema={
                "type": "object",
                "properties": {
                    "since": {
                        "type": "string",
                        "description": "Only entries since this window (e.g. 24h, 7d, 2w).",
                    },
                    "action": {"type": "string", "description": "Filter by action name."},
                    "limit": {"type": "integer", "description": "Max entries (default 20)."},
                },
            },
            handler=_tool_audit_query,
        )
    )
    return server


def serve_stdio() -> None:
    """Entry point for ``atlas mcp serve`` — run the Atlas server over stdio."""
    build_atlas_server().serve()
