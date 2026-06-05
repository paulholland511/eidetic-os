"""A minimal Model Context Protocol (MCP) client.

The Atlas OS runtime uses this to launch and talk to MCP servers — both the
bundled skill servers (over **stdio**, a subprocess) and remote/team servers
(over **HTTP**, optionally Server-Sent-Events framed). It implements the client
half of the handshake the spec requires:

    initialize → notifications/initialized → tools/list → tools/call

Design notes:

* **Synchronous.** Atlas OS is a one-shot CLI; a blocking request/response client
  matches the rest of the codebase and avoids an asyncio dependency.
* **Two transports, one interface.** :class:`StdioTransport` frames messages as
  newline-delimited JSON on a subprocess's stdin/stdout; :class:`HttpTransport`
  POSTs each JSON-RPC request and accepts either a plain ``application/json`` or
  a ``text/event-stream`` (SSE) response, extracting the JSON-RPC reply from it.
* **No new dependencies.** stdio uses :mod:`subprocess`; HTTP uses ``requests``
  (already a core dependency).

Typical use::

    with MCPClient(StdioTransport([sys.executable, "-m", "atlas_os", "mcp", "serve"])) as client:
        client.initialize()
        tools = client.list_tools()
        result = client.call_tool("search", {"query": "kelly criterion"})
"""

from __future__ import annotations

import json
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any

from atlas_os.mcp_server import PROTOCOL_VERSION


class MCPClientError(RuntimeError):
    """Raised when a server returns a JSON-RPC error or the transport fails."""


@dataclass(frozen=True)
class ToolInfo:
    """A tool advertised by a server's ``tools/list`` response."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a ``tools/call`` — its text content and error flag."""

    text: str
    is_error: bool
    raw: dict[str, Any]


# ── Transports ────────────────────────────────────────────────────────────────
class Transport(ABC):
    """Send a JSON-RPC request and (for requests with an id) read the response."""

    @abstractmethod
    def request(self, message: Mapping[str, Any]) -> dict[str, Any]:
        """Send a request message and return the response object."""

    @abstractmethod
    def notify(self, message: Mapping[str, Any]) -> None:
        """Send a notification (no response expected)."""

    @abstractmethod
    def close(self) -> None:
        """Release the transport (terminate subprocess / close session)."""


class StdioTransport(Transport):
    """Launch an MCP server as a subprocess and frame messages over stdio.

    Each message is a single line of JSON on the child's stdin; each response is
    a single line on its stdout (MCP's stdio framing). The child's stderr is left
    attached to ours so server diagnostics surface during development.
    """

    def __init__(self, command: Sequence[str], *, env: Mapping[str, str] | None = None) -> None:
        self._command = list(command)
        self._proc = subprocess.Popen(  # noqa: S603 - command is caller-supplied, trusted
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
            env=dict(env) if env is not None else None,
        )

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._proc.stdin is None:  # pragma: no cover - PIPE is always set above
            raise MCPClientError("server stdin is not available")
        self._proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def request(self, message: Mapping[str, Any]) -> dict[str, Any]:
        self._send(message)
        if self._proc.stdout is None:  # pragma: no cover
            raise MCPClientError("server stdout is not available")
        # Read until we get a non-blank line (the response). EOF → the server died.
        while True:
            line = self._proc.stdout.readline()
            if line == "":
                raise MCPClientError("server closed the connection before responding")
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                raise MCPClientError(f"malformed response from server: {line!r}") from exc

    def notify(self, message: Mapping[str, Any]) -> None:
        self._send(message)

    def close(self) -> None:
        proc = self._proc
        if proc.poll() is None:
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - slow shutdown
                proc.kill()


class HttpTransport(Transport):
    """Talk to a remote MCP server over HTTP, accepting JSON or SSE responses.

    Each request is POSTed as a JSON-RPC body; the response may be a plain JSON
    object or a ``text/event-stream`` carrying the reply in a ``data:`` field
    (the streamable-HTTP transport). Notifications are POSTed and the (typically
    202/empty) response is discarded.
    """

    def __init__(self, url: str, *, headers: Mapping[str, str] | None = None, timeout: float = 60.0) -> None:
        import requests

        self._url = url
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        )
        if headers:
            self._session.headers.update(dict(headers))

    def request(self, message: Mapping[str, Any]) -> dict[str, Any]:
        response = self._session.post(self._url, json=message, timeout=self._timeout)
        if response.status_code >= 400:
            raise MCPClientError(f"HTTP {response.status_code} from {self._url}: {response.text[:200]}")
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            return _parse_sse(response.text)
        try:
            return response.json()
        except ValueError as exc:
            raise MCPClientError(f"non-JSON response from {self._url}: {response.text[:200]}") from exc

    def notify(self, message: Mapping[str, Any]) -> None:
        self._session.post(self._url, json=message, timeout=self._timeout)

    def close(self) -> None:
        self._session.close()


def _parse_sse(text: str) -> dict[str, Any]:
    """Extract the first JSON-RPC object from an SSE (``data:``-framed) body."""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    raise MCPClientError("no JSON-RPC object found in SSE response")


# ── Client ────────────────────────────────────────────────────────────────────
class MCPClient:
    """A synchronous MCP client over a :class:`Transport`.

    Use as a context manager so the transport (and any subprocess) is always
    torn down. :meth:`initialize` must be called before :meth:`list_tools` /
    :meth:`call_tool`; it performs the handshake and the post-init notification.
    """

    def __init__(self, transport: Transport, *, client_name: str = "atlas-os", client_version: str = "0.0.0") -> None:
        self._transport = transport
        self._client_name = client_name
        self._client_version = client_version
        self._next_id = 0
        self._initialized = False
        self.server_info: dict[str, Any] = {}

    def __enter__(self) -> MCPClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _rpc(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
        response = self._transport.request(message)
        if "error" in response:
            err = response["error"]
            raise MCPClientError(f"{method} failed: {err.get('message', err)} (code {err.get('code')})")
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPClientError(f"{method} returned no result object")
        return result

    def initialize(self) -> dict[str, Any]:
        """Perform the MCP handshake; returns the server's ``initialize`` result."""
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self._client_name, "version": self._client_version},
            },
        )
        self.server_info = result.get("serverInfo", {})
        self._transport.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        return result

    def list_tools(self) -> list[ToolInfo]:
        """Return the tools the server advertises (calls ``tools/list``)."""
        self._ensure_initialized()
        result = self._rpc("tools/list")
        tools: list[ToolInfo] = []
        for entry in result.get("tools", []):
            if not isinstance(entry, Mapping):
                continue
            tools.append(
                ToolInfo(
                    name=str(entry.get("name", "")),
                    description=str(entry.get("description", "")),
                    input_schema=dict(entry.get("inputSchema") or {}),
                )
            )
        return tools

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> ToolResult:
        """Invoke a tool by name with ``arguments`` (calls ``tools/call``)."""
        self._ensure_initialized()
        result = self._rpc("tools/call", {"name": name, "arguments": dict(arguments or {})})
        return ToolResult(
            text=_content_text(result.get("content")),
            is_error=bool(result.get("isError", False)),
            raw=result,
        )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise MCPClientError("call initialize() before using the client")

    def close(self) -> None:
        self._transport.close()


def _content_text(content: Any) -> str:
    """Flatten an MCP content array into a single text string."""
    if not isinstance(content, list):
        return ""
    parts = [str(block.get("text", "")) for block in content if isinstance(block, Mapping) and block.get("type") == "text"]
    return "\n".join(p for p in parts if p)


def transport_from_manifest(config: Mapping[str, Any]) -> Transport:
    """Build a :class:`Transport` from a skill's ``mcp_server`` manifest block.

    ``{transport: stdio, command: [...], env: {...}}`` launches a subprocess;
    ``{transport: http|sse, url: "...", headers: {...}}`` connects to a remote
    server. Shape is assumed valid (the marketplace validates it at publish
    time); a bad block raises :class:`MCPClientError`.
    """
    transport = str(config.get("transport", "stdio"))
    if transport == "stdio":
        command = config.get("command")
        if not isinstance(command, Sequence) or isinstance(command, str) or not command:
            raise MCPClientError("stdio transport needs a non-empty 'command' list")
        env = config.get("env")
        return StdioTransport(
            [str(c) for c in command],
            env={str(k): str(v) for k, v in env.items()} if isinstance(env, Mapping) else None,
        )
    if transport in ("http", "sse"):
        url = config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise MCPClientError(f"{transport} transport needs a 'url'")
        headers = config.get("headers")
        return HttpTransport(
            url,
            headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, Mapping) else None,
        )
    raise MCPClientError(f"unknown transport {transport!r}")
