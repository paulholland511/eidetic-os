"""Channel adapter framework — bridge Eidetic OS to Slack, Telegram, or a webhook.

A channel turns a messaging surface into a query interface over your memory:
inbound messages are routed through the fact store / RAG search (see
:func:`eidetic_os.channels.base.make_rag_router`) and the answer is sent back.

This package is the registry and the public entry points. Adapters live in
sibling modules and register a *factory* here:

* ``webhook``  — :mod:`eidetic_os.channels.webhook`  (no external dependencies)
* ``slack``    — :mod:`eidetic_os.channels.slack`    (needs ``slack-sdk``)
* ``telegram`` — :mod:`eidetic_os.channels.telegram` (needs ``python-telegram-bot``)

Configuration is read from ``.eidetic/channels.yaml`` — a mapping of channel name
to that channel's settings, e.g.::

    webhook:
      host: 127.0.0.1
      port: 8765
    slack:
      bot_token: xoxb-…
      channel: "#general"

The heavy optional dependencies are imported lazily inside each adapter, so
importing this package (and listing channels) never requires ``slack-sdk`` or
``python-telegram-bot`` to be installed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from eidetic_os.channels.base import (
    Channel,
    ChannelError,
    Handler,
    make_rag_router,
)

# A factory builds a channel from its config dict. Adapters register one under
# their name; ``create`` looks it up. Kept as factories (not classes) so an
# adapter module is only imported when its channel is actually used.
ChannelFactory = Callable[[dict[str, Any]], Channel]

_REGISTRY: dict[str, ChannelFactory] = {}

# The built-in adapters and the module path of their factory. Resolved lazily on
# first use so a missing optional dependency never breaks `channels list`.
_BUILTINS: dict[str, str] = {
    "webhook": "eidetic_os.channels.webhook:make_webhook_channel",
    "slack": "eidetic_os.channels.slack:make_slack_channel",
    "telegram": "eidetic_os.channels.telegram:make_telegram_channel",
}

CHANNELS_FILENAME = "channels.yaml"


def register(name: str, factory: ChannelFactory) -> None:
    """Register a channel factory under ``name`` (overrides any existing one)."""
    _REGISTRY[name] = factory


def available_channels() -> tuple[str, ...]:
    """Every known channel name — registered factories plus the built-ins."""
    return tuple(sorted(set(_REGISTRY) | set(_BUILTINS)))


def _resolve_factory(name: str) -> ChannelFactory:
    """Return the factory for ``name``, importing its built-in module on demand."""
    if name in _REGISTRY:
        return _REGISTRY[name]
    target = _BUILTINS.get(name)
    if target is None:
        raise ChannelError(
            f"unknown channel {name!r} — known: {', '.join(available_channels())}"
        )
    module_path, _, attr = target.partition(":")
    import importlib

    module = importlib.import_module(module_path)
    factory: ChannelFactory = getattr(module, attr)
    _REGISTRY[name] = factory
    return factory


def create_channel(
    name: str, config: dict[str, Any] | None = None
) -> Channel:
    """Construct the channel ``name`` from ``config`` (or its config-file section).

    When ``config`` is omitted the channel's section of ``.eidetic/channels.yaml``
    is used. Raises :class:`ChannelError` for an unknown channel or a missing
    optional dependency.
    """
    settings = config if config is not None else load_channels_config().get(name, {})
    factory = _resolve_factory(name)
    channel = factory(dict(settings))
    channel.name = name
    return channel


# ── Configuration file ──────────────────────────────────────────────────────────

def channels_config_path() -> Path:
    """Resolve ``channels.yaml`` like the fact store: env → vault → cwd.

    Order: ``EIDETIC_CHANNELS_PATH`` → ``$VAULT_PATH/.eidetic/channels.yaml`` →
    ``./.eidetic/channels.yaml``.
    """
    override = os.environ.get("EIDETIC_CHANNELS_PATH")
    if override:
        return Path(os.path.expanduser(override))
    vault = os.environ.get("VAULT_PATH")
    base = Path(os.path.expanduser(vault)) if vault else Path.cwd()
    return base / ".eidetic" / CHANNELS_FILENAME


def load_channels_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the channel config mapping, or ``{}`` if absent/malformed.

    Never raises: a missing file or bad YAML yields an empty mapping. Only
    sections that are themselves mappings are kept.
    """
    target = path or channels_config_path()
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def configured_channels(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """The channels that actually have a config section (what ``channels list`` shows)."""
    return load_channels_config(path)


__all__ = [
    "Channel",
    "ChannelError",
    "ChannelFactory",
    "Handler",
    "available_channels",
    "channels_config_path",
    "configured_channels",
    "create_channel",
    "load_channels_config",
    "make_rag_router",
    "register",
]
