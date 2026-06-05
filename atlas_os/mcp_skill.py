"""Wrap Atlas OS ``SKILL.md`` skills as MCP tools — no skill changes required.

Atlas skills are prompt-based: a ``SKILL.md`` is a YAML-frontmatter header (name,
description) plus a markdown body of instructions, carrying ``{{PLACEHOLDER}}``
tokens that are filled from the environment. This module makes those skills
**MCP-compatible** without touching a single one of them:

* :func:`skill_to_tool` projects one :class:`~atlas_os._skills.Skill` into an MCP
  :class:`~atlas_os.mcp_server.Tool`. Calling the tool renders the skill's
  ``SKILL.md`` (placeholders substituted from the environment, optionally
  overridden by a ``placeholders`` argument) and returns it — i.e. an MCP host
  asks for the skill and gets back its ready-to-run instructions.
* :func:`build_skill_server` auto-generates an MCP server shim exposing every
  skill (or a chosen subset) as tools, reusing the :class:`MCPServer` core. This
  is what ``atlas skills run <name>`` launches.

Because the tool surface is derived from the existing frontmatter, every skill
that already ships works through the MCP layer unmodified — the backwards-
compatibility guarantee the issue asks for.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from atlas_os._skills import (
    Skill,
    _parse_frontmatter,
    load_skills,
    skill_source,
    substitute_placeholders,
)
from atlas_os.mcp_server import MCPServer, Tool

# MCP tool names must be a safe slug; Atlas skill slugs already are ([a-z0-9-]).
# We sanitise defensively in case a third-party skill folder uses other chars.
_TOOL_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def tool_name_for(slug: str) -> str:
    """Map a skill slug to a valid MCP tool name."""
    return _TOOL_NAME_RE.sub("-", slug).strip("-") or "skill"


def _skill_input_schema() -> dict[str, Any]:
    """The input schema shared by every skill tool — optional placeholder overrides."""
    return {
        "type": "object",
        "properties": {
            "placeholders": {
                "type": "object",
                "description": (
                    "Optional map of {{PLACEHOLDER}} token → value, overriding the "
                    "environment when rendering the skill's instructions."
                ),
            }
        },
        "additionalProperties": False,
    }


def _render_skill(slug: str, overrides: Mapping[str, str]) -> str:
    """Render a skill's SKILL.md with placeholders filled from env + overrides."""
    source = skill_source(slug)
    if not source.is_file():
        raise FileNotFoundError(f"no SKILL.md for skill {slug!r}")
    text = source.read_text(encoding="utf-8")

    import os

    env: dict[str, str] = dict(os.environ)
    env.update({str(k): str(v) for k, v in overrides.items()})
    rendered, _resolved, unresolved = substitute_placeholders(text, env)
    if unresolved:
        note = ", ".join(unresolved)
        rendered += f"\n\n<!-- unresolved placeholders (fill these in): {note} -->"
    return rendered


def skill_to_tool(skill: Skill) -> Tool:
    """Project one skill into an MCP tool whose call returns its rendered instructions."""

    def handler(arguments: Mapping[str, Any]) -> str:
        raw_overrides = arguments.get("placeholders") or {}
        overrides = raw_overrides if isinstance(raw_overrides, Mapping) else {}
        return _render_skill(skill.slug, overrides)

    description = skill.description or f"Run the {skill.name} skill."
    return Tool(
        name=tool_name_for(skill.slug),
        description=description,
        input_schema=_skill_input_schema(),
        handler=handler,
    )


def build_skill_server(slugs: Sequence[str] | None = None) -> MCPServer:
    """Build an MCP server exposing skills as tools.

    With ``slugs`` given, only those skills are exposed (and an unknown slug
    raises :class:`LookupError`); otherwise every discovered skill is exposed.
    The server name reflects its contents so a host can tell a single-skill
    server (``atlas skills run <name>``) from the full catalog.
    """
    from atlas_os import __version__

    available = {s.slug: s for s in load_skills()}

    if slugs is None:
        chosen = list(available.values())
        name = "atlas-skills"
    else:
        chosen = []
        for slug in slugs:
            skill = available.get(slug)
            if skill is None:
                raise LookupError(f"unknown skill {slug!r}")
            chosen.append(skill)
        name = f"atlas-skill-{slugs[0]}" if len(slugs) == 1 else "atlas-skills"

    server = MCPServer(name=name, version=__version__)
    for skill in chosen:
        server.add_tool(skill_to_tool(skill))
    return server


def serve_skill(slug: str) -> None:
    """Entry point for ``atlas skills run <name>`` — serve one skill over stdio."""
    build_skill_server([slug]).serve()


def mcp_server_config(slug: str) -> dict[str, Any] | None:
    """Return a skill's declared ``mcp_server`` transport block, or None.

    A skill is an *MCP-server skill* (rather than a plain prompt skill) when its
    SKILL.md frontmatter carries an ``mcp_server`` object — e.g. a bundled tool
    server launched over stdio, or a remote team server reached over HTTP/SSE.
    The marketplace validates the block's shape at publish time; here we just
    read it back for the runtime to build a transport from.
    """
    source = skill_source(slug)
    if not source.is_file():
        return None
    meta = _parse_frontmatter(source.read_text(encoding="utf-8"))
    config = meta.get("mcp_server")
    return dict(config) if isinstance(config, dict) else None
