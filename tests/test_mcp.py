"""Tests for the MCP (Model Context Protocol) layer.

Covers the four moving parts the issue asks for:

* the server core (:mod:`atlas_os.mcp_server`) — handshake, tool discovery,
  dispatch, argument validation, and tool-error reporting;
* the client (:mod:`atlas_os.mcp_client`) — driven both in-process against a
  loopback transport and end-to-end against a real subprocess over stdio;
* the skill wrapper (:mod:`atlas_os.mcp_skill`) — every existing skill exposed
  as an MCP tool, unmodified (the backwards-compatibility guarantee);
* the marketplace's ``mcp_server`` manifest support.

These are hermetic: the in-process tests never spawn anything, and the single
stdio round-trip test launches ``python -m atlas_os skills run`` with the same
interpreter, reading/writing JSON-RPC lines — no network, no real vault writes.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

import pytest

from atlas_os import mcp_client, mcp_server, mcp_skill
from atlas_os.mcp_client import (
    MCPClient,
    MCPClientError,
    StdioTransport,
    Transport,
    transport_from_manifest,
)
from atlas_os.mcp_server import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    MCPServer,
    Tool,
    build_atlas_server,
    validate_arguments,
)


# ── A trivial server used across the protocol tests ───────────────────────────
def _echo_server() -> MCPServer:
    server = MCPServer(name="test-server", version="9.9.9")
    server.add_tool(
        Tool(
            name="echo",
            description="Echo the 'text' argument back.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=lambda args: f"echo: {args['text']}",
        )
    )
    server.add_tool(
        Tool(
            name="boom",
            description="Always raises.",
            input_schema={"type": "object", "properties": {}},
            handler=_raise,
        )
    )
    return server


def _raise(_args: Mapping[str, Any]) -> str:
    raise ValueError("kaboom")


# ── A loopback transport so the client can be tested without a subprocess ──────
class LoopbackTransport(Transport):
    """Route client requests straight into a server's ``handle_message``."""

    def __init__(self, server: MCPServer) -> None:
        self._server = server
        self.closed = False

    def request(self, message: Mapping[str, Any]) -> dict[str, Any]:
        response = self._server.handle_message(message)
        assert response is not None  # requests always get a response
        return response

    def notify(self, message: Mapping[str, Any]) -> None:
        self._server.handle_message(message)

    def close(self) -> None:
        self.closed = True


# ──────────────────────────────────────────────────────────────────────────────
# Server core
# ──────────────────────────────────────────────────────────────────────────────
def test_initialize_handshake_echoes_protocol_and_identity() -> None:
    server = _echo_server()
    resp = server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}
    )
    assert resp is not None
    result = resp["result"]
    assert result["protocolVersion"] == "2025-03-26"  # client's choice echoed back
    assert result["serverInfo"] == {"name": "test-server", "version": "9.9.9"}
    assert "tools" in result["capabilities"]


def test_initialize_defaults_protocol_when_unspecified() -> None:
    resp = _echo_server().handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp is not None
    assert resp["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION


def test_tools_list_returns_definitions() -> None:
    resp = _echo_server().handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert resp is not None
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"echo", "boom"}
    echo = next(t for t in resp["result"]["tools"] if t["name"] == "echo")
    assert echo["inputSchema"]["required"] == ["text"]


def test_tools_call_success() -> None:
    resp = _echo_server().handle_message(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "hi"}}}
    )
    assert resp is not None
    result = resp["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"] == "echo: hi"


def test_tools_call_missing_required_argument_is_tool_error() -> None:
    resp = _echo_server().handle_message(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "echo", "arguments": {}}}
    )
    assert resp is not None
    assert resp["result"]["isError"] is True
    assert "missing required argument 'text'" in resp["result"]["content"][0]["text"]


def test_tools_call_handler_exception_becomes_tool_error() -> None:
    resp = _echo_server().handle_message(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "boom", "arguments": {}}}
    )
    assert resp is not None
    assert resp["result"]["isError"] is True
    assert "ValueError: kaboom" in resp["result"]["content"][0]["text"]


def test_unknown_tool_is_protocol_error() -> None:
    resp = _echo_server().handle_message(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "ghost"}}
    )
    assert resp is not None
    assert resp["error"]["code"] == INVALID_PARAMS


def test_unknown_method_is_method_not_found() -> None:
    resp = _echo_server().handle_message({"jsonrpc": "2.0", "id": 7, "method": "does/not/exist"})
    assert resp is not None
    assert resp["error"]["code"] == METHOD_NOT_FOUND


def test_notifications_get_no_response() -> None:
    server = _echo_server()
    assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    # A request-shaped message with no id is a notification too.
    assert server.handle_message({"jsonrpc": "2.0", "method": "tools/list"}) is None


def test_ping_returns_empty_result() -> None:
    resp = _echo_server().handle_message({"jsonrpc": "2.0", "id": 8, "method": "ping"})
    assert resp is not None
    assert resp["result"] == {}


def test_add_tool_overrides_same_name() -> None:
    server = MCPServer(name="s", version="0")
    server.add_tool(Tool("t", "first", {"type": "object", "properties": {}}, lambda a: "1"))
    server.add_tool(Tool("t", "second", {"type": "object", "properties": {}}, lambda a: "2"))
    assert len(server.tools) == 1
    assert server.tools[0].description == "second"


# ── validate_arguments unit coverage ──────────────────────────────────────────
def test_validate_arguments_type_checks() -> None:
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "s": {"type": "string"}},
        "required": ["n"],
    }
    assert validate_arguments(schema, {"n": 3, "s": "x"}) == []
    assert validate_arguments(schema, {}) == ["missing required argument 'n'"]
    assert validate_arguments(schema, {"n": "no"}) == ["argument 'n' must be a integer"]


def test_validate_arguments_rejects_bool_as_integer() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
    # bool is a subclass of int; the validator must not accept True as an integer.
    assert validate_arguments(schema, {"n": True}) == ["argument 'n' must be a integer"]


# ──────────────────────────────────────────────────────────────────────────────
# Client (loopback — no subprocess)
# ──────────────────────────────────────────────────────────────────────────────
def test_client_initialize_list_call_via_loopback() -> None:
    transport = LoopbackTransport(_echo_server())
    with MCPClient(transport) as client:
        init = client.initialize()
        assert init["serverInfo"]["name"] == "test-server"
        tools = client.list_tools()
        assert {t.name for t in tools} == {"echo", "boom"}
        result = client.call_tool("echo", {"text": "world"})
        assert result.is_error is False
        assert result.text == "echo: world"
    assert transport.closed is True


def test_client_requires_initialize_first() -> None:
    with MCPClient(LoopbackTransport(_echo_server())) as client:
        with pytest.raises(MCPClientError):
            client.list_tools()


def test_client_surfaces_protocol_error_as_exception() -> None:
    with MCPClient(LoopbackTransport(_echo_server())) as client:
        client.initialize()
        with pytest.raises(MCPClientError):
            client.call_tool("ghost", {})


def test_client_reports_handler_error_as_tool_result() -> None:
    with MCPClient(LoopbackTransport(_echo_server())) as client:
        client.initialize()
        result = client.call_tool("boom", {})
        assert result.is_error is True
        assert "kaboom" in result.text


# ──────────────────────────────────────────────────────────────────────────────
# Stdio round-trip — a real subprocess over the wire
# ──────────────────────────────────────────────────────────────────────────────
def test_stdio_round_trip_against_atlas_server() -> None:
    transport = StdioTransport([sys.executable, "-m", "atlas_os", "mcp", "serve"])
    with MCPClient(transport) as client:
        client.initialize()
        assert client.server_info["name"] == "atlas-os"
        names = {t.name for t in client.list_tools()}
        assert {"search", "embed", "doctor", "skills_list", "audit_query"} <= names
        result = client.call_tool("skills_list", {})
        assert result.is_error is False
        assert '"skills"' in result.text


def test_stdio_round_trip_serves_a_skill() -> None:
    skills = mcp_skill.load_skills()
    assert skills, "expected at least one bundled skill"
    slug = skills[0].slug
    transport = StdioTransport([sys.executable, "-m", "atlas_os", "skills", "run", slug])
    with MCPClient(transport) as client:
        client.initialize()
        tools = client.list_tools()
        assert [t.name for t in tools] == [mcp_skill.tool_name_for(slug)]
        result = client.call_tool(mcp_skill.tool_name_for(slug), {})
        assert result.is_error is False
        assert result.text.startswith("---")  # the SKILL.md frontmatter


# ──────────────────────────────────────────────────────────────────────────────
# Skill wrapper — existing skills work through MCP unmodified
# ──────────────────────────────────────────────────────────────────────────────
def test_tool_name_sanitises_slug() -> None:
    assert mcp_skill.tool_name_for("daily-trading-report") == "daily-trading-report"
    assert mcp_skill.tool_name_for("weird name!") == "weird-name"


def test_skill_server_exposes_every_skill() -> None:
    skills = mcp_skill.load_skills()
    server = mcp_skill.build_skill_server()
    assert {t.name for t in server.tools} == {mcp_skill.tool_name_for(s.slug) for s in skills}


def test_skill_tool_renders_skill_md() -> None:
    skill = mcp_skill.load_skills()[0]
    tool = mcp_skill.skill_to_tool(skill)
    text = tool.handler({})
    assert text.startswith("---")
    assert skill.name in text or "name:" in text


def test_skill_tool_applies_placeholder_overrides() -> None:
    # Find a skill whose SKILL.md actually uses a placeholder so the override is
    # observable; fall back to asserting render works if none do.
    for skill in mcp_skill.load_skills():
        raw = mcp_skill.skill_source(skill.slug).read_text(encoding="utf-8")
        if "{{VAULT_PATH}}" in raw:
            tool = mcp_skill.skill_to_tool(skill)
            rendered = tool.handler({"placeholders": {"VAULT_PATH": "/tmp/sentinel-vault"}})
            assert "/tmp/sentinel-vault" in rendered
            assert "{{VAULT_PATH}}" not in rendered
            return
    pytest.skip("no bundled skill uses {{VAULT_PATH}}")


def test_build_skill_server_unknown_slug_raises() -> None:
    with pytest.raises(LookupError):
        mcp_skill.build_skill_server(["no-such-skill"])


def test_single_skill_server_is_named_for_the_skill() -> None:
    slug = mcp_skill.load_skills()[0].slug
    server = mcp_skill.build_skill_server([slug])
    assert server.name == f"atlas-skill-{slug}"
    assert len(server.tools) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Atlas server tools (in-process, no shelling out)
# ──────────────────────────────────────────────────────────────────────────────
def test_atlas_server_skills_list_tool() -> None:
    import json

    server = build_atlas_server()
    resp = server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "skills_list", "arguments": {}}}
    )
    assert resp is not None
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["count"] == len(mcp_skill.load_skills())


# ──────────────────────────────────────────────────────────────────────────────
# Marketplace mcp_server manifest support
# ──────────────────────────────────────────────────────────────────────────────
def test_manifest_parses_mcp_server_block() -> None:
    from atlas_os.marketplace import manifest_from_frontmatter

    meta = {
        "name": "remote-skill",
        "description": "A remote MCP skill.",
        "mcp_server": {"transport": "http", "url": "https://example.com/mcp"},
    }
    manifest = manifest_from_frontmatter(meta)
    assert manifest.is_mcp_server is True
    assert manifest.mcp_server is not None
    assert manifest.mcp_server["url"] == "https://example.com/mcp"
    assert manifest.to_dict()["mcp_server"]["transport"] == "http"


def test_plain_skill_manifest_has_no_mcp_server() -> None:
    from atlas_os.marketplace import manifest_from_frontmatter

    manifest = manifest_from_frontmatter({"name": "plain", "description": "A prompt skill."})
    assert manifest.is_mcp_server is False
    assert "mcp_server" not in manifest.to_dict()


def test_mcp_server_validation_accepts_valid_blocks() -> None:
    from atlas_os.marketplace import _mcp_server_problems

    assert _mcp_server_problems(None) == []
    assert _mcp_server_problems({"transport": "stdio", "command": ["atlas", "skills", "run", "x"]}) == []
    assert _mcp_server_problems({"transport": "sse", "url": "https://team/mcp"}) == []


def test_mcp_server_validation_rejects_bad_blocks() -> None:
    from atlas_os.marketplace import _mcp_server_problems

    assert _mcp_server_problems("nope")  # not an object
    assert _mcp_server_problems({"transport": "carrier-pigeon"})  # bad transport
    assert _mcp_server_problems({"transport": "stdio"})  # stdio needs a command
    assert _mcp_server_problems({"transport": "http"})  # http needs a url


def test_validate_skill_rejects_malformed_mcp_server(tmp_path: Any) -> None:
    from atlas_os.marketplace import SkillValidationError, validate_skill

    skill_dir = tmp_path / "broken-mcp"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: broken-mcp\ndescription: Bad MCP block.\n"
        "mcp_server:\n  transport: stdio\n---\nBody.\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillValidationError) as exc:
        validate_skill(skill_dir)
    assert any("mcp_server.command" in p for p in exc.value.problems)


# ── Transport factory ─────────────────────────────────────────────────────────
def test_transport_from_manifest_builds_stdio() -> None:
    transport = transport_from_manifest({"transport": "stdio", "command": [sys.executable, "-c", "pass"]})
    try:
        assert isinstance(transport, StdioTransport)
    finally:
        transport.close()


def test_transport_from_manifest_builds_http() -> None:
    transport = transport_from_manifest({"transport": "http", "url": "https://example.com/mcp"})
    try:
        assert isinstance(transport, mcp_client.HttpTransport)
    finally:
        transport.close()


def test_transport_from_manifest_rejects_unknown() -> None:
    with pytest.raises(MCPClientError):
        transport_from_manifest({"transport": "telepathy"})
