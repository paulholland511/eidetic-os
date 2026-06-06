"""The abstract :class:`Channel` contract and the inbound message router.

A *channel* is a two-way bridge between Eidetic OS and a messaging surface (Slack,
Telegram, a bare webhook). Every adapter implements the same small async
lifecycle — :meth:`Channel.connect`, :meth:`Channel.send`,
:meth:`Channel.on_message`, :meth:`Channel.disconnect` — so the CLI and tests
drive any channel identically.

Inbound messages are answered by a **handler**: a callable that takes the
message text and returns a reply string. The default handler
(:func:`make_rag_router`) routes the text through the fact store (and, when
available, RAG search) and formats the hits — turning any connected channel into
a query interface over your memory. Handlers may be sync or async;
:meth:`Channel.reply` normalises both.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

# A handler maps an inbound message to a reply. Either flavour is accepted; the
# channel awaits the result when it's a coroutine.
Handler = Callable[[str], "str | Awaitable[str]"]


class ChannelError(RuntimeError):
    """A channel could not be constructed, connected, or driven."""


class Channel(ABC):
    """Abstract two-way messaging bridge.

    Concrete adapters set :attr:`name`, accept their settings as a ``config``
    dict, and implement the four lifecycle methods. A registered handler (set via
    :meth:`on_message`) answers inbound messages; :meth:`reply` is the helper
    adapters call to run it.
    """

    name: str = "channel"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = dict(config or {})
        self._handler: Handler | None = None

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection / start listening. Idempotent where it can be."""

    @abstractmethod
    async def send(self, message: str) -> None:
        """Send ``message`` outbound on this channel."""

    @abstractmethod
    async def on_message(self, handler: Handler) -> None:
        """Register the callable that answers inbound messages."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear the connection down and release resources. Safe to call twice."""

    # ── shared helpers ──────────────────────────────────────────────────────────
    async def reply(self, text: str) -> str:
        """Run the registered handler against ``text`` and return its reply.

        Returns an empty string if no handler is registered. Tolerates both sync
        and async handlers, so an adapter never has to care which it was given.
        """
        if self._handler is None:
            return ""
        result = self._handler(text)
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    def reply_sync(self, text: str) -> str:
        """Synchronously run the handler — for adapters whose inbound path is a thread.

        Used by the webhook server, which dispatches from a plain (non-async)
        request-handler thread. Drives an async handler via a private event loop.
        """
        if self._handler is None:
            return ""
        result = self._handler(text)
        if inspect.isawaitable(result):
            import asyncio

            return str(asyncio.run(result))  # type: ignore[arg-type]
        return str(result)


# ── Inbound routing: text → an answer from memory ───────────────────────────────

# A search returns (label, score, text) triples; injectable so the router is
# testable without a store, embeddings, or the network.
FactSearch = Callable[[str, int], list[tuple[str, float, str]]]


def _default_fact_search(query: str, limit: int) -> list[tuple[str, float, str]]:
    """Search the conventional fact store, degrading to offline token overlap."""
    from eidetic_os import facts

    with facts.open_store(with_embedder=True) as store:
        hits = store.query_facts(query, limit=limit)
    return [(f.category, score, f.fact) for f, score in hits]


def make_rag_router(
    *,
    fact_search: FactSearch | None = None,
    limit: int = 5,
    greeting: str = "Eidetic OS — ask me anything about your notes and memory.",
) -> Handler:
    """Build the default inbound handler: route a query through memory.

    The returned handler runs ``fact_search`` (the fact store by default) and
    formats the top hits as a plain bulleted list — the format the user prefers
    for chat surfaces. Empty input returns a greeting; no hits returns a clear
    "nothing found" so the channel always answers something.
    """
    search = fact_search or _default_fact_search

    def route(text: str) -> str:
        query = text.strip()
        if not query:
            return greeting
        try:
            hits = search(query, limit)
        except Exception as exc:  # noqa: BLE001 - a search failure must still answer
            return f"⚠ search failed: {exc}"
        if not hits:
            return f"No matching facts for “{query}”."
        lines = [f"Top {len(hits)} for “{query}”:"]
        for label, score, fact in hits:
            lines.append(f"• [{label}] {fact}  ({score:.2f})")
        return "\n".join(lines)

    return route
