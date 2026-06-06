"""Generic webhook channel — receive messages over HTTP, no external dependencies.

The webhook adapter runs a tiny :mod:`http.server` in a background thread. POST a
JSON body ``{"message": "your query"}`` to it and it routes the text through the
registered handler (the RAG/fact router by default) and returns
``{"reply": "…"}``. This is the dependency-free way to wire any system that can
make an HTTP request — a shell script, a Shortcut, another service — into Eidetic
OS memory.

Outbound :meth:`WebhookChannel.send` POSTs to an optional ``outbound_url`` (e.g. a
Slack/Discord incoming-webhook URL); with none configured it simply records the
last sent message, which keeps the channel fully testable offline.

Config keys (all optional):

* ``host``         — interface to bind (default ``127.0.0.1``; localhost only).
* ``port``         — port to listen on (default ``8765``; ``0`` picks a free one).
* ``path``         — URL path that accepts posts (default ``/``).
* ``outbound_url`` — where :meth:`send` POSTs, if anywhere.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from eidetic_os.channels.base import Channel, ChannelError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PATH = "/"


class WebhookChannel(Channel):
    """A channel backed by a local HTTP server (inbound) + optional outbound POST."""

    name = "webhook"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.host = str(self.config.get("host", DEFAULT_HOST))
        self.port = int(self.config.get("port", DEFAULT_PORT))
        self.path = str(self.config.get("path", DEFAULT_PATH))
        self.outbound_url = self.config.get("outbound_url")
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.last_sent: str | None = None

    @property
    def bound_port(self) -> int | None:
        """The actual port the server is listening on (resolves ``port: 0``)."""
        return self._server.server_address[1] if self._server is not None else None

    async def connect(self) -> None:
        """Start the HTTP server in a daemon thread (idempotent)."""
        if self._server is not None:
            return
        channel = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server naming
                if self.path.rstrip("/") not in ("", channel.path.rstrip("/")):
                    self._json(404, {"error": "not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._json(400, {"error": "invalid JSON"})
                    return
                text = str(body.get("message", "")) if isinstance(body, dict) else ""
                reply = channel.reply_sync(text)
                self._json(200, {"reply": reply})

            def _json(self, status: int, obj: object) -> None:
                payload = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args: object) -> None:
                return  # silence the access log

        try:
            self._server = HTTPServer((self.host, self.port), _Handler)
        except OSError as exc:
            raise ChannelError(
                f"webhook could not bind {self.host}:{self.port} ({exc})"
            ) from exc
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="eidetic-webhook", daemon=True
        )
        self._thread.start()

    async def send(self, message: str) -> None:
        """POST ``message`` to ``outbound_url`` if set; otherwise record it locally."""
        self.last_sent = message
        if not self.outbound_url:
            return
        import requests

        try:
            requests.post(self.outbound_url, json={"text": message}, timeout=10)
        except requests.RequestException as exc:
            raise ChannelError(f"webhook outbound POST failed: {exc}") from exc

    async def on_message(self, handler) -> None:  # type: ignore[override]
        self._handler = handler

    async def disconnect(self) -> None:
        """Stop the server and join the thread (safe to call when never started)."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def make_webhook_channel(config: dict[str, Any]) -> Channel:
    """Factory registered under ``webhook`` (see :mod:`eidetic_os.channels`)."""
    return WebhookChannel(config)
