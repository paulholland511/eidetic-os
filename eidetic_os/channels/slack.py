"""Slack channel adapter — outbound via Web API, inbound via Socket Mode.

Needs the optional ``slack-sdk`` dependency (``pip install 'eidetic-os[slack]'``).
The import is lazy and guarded, so listing channels never requires it; the clear
:class:`ChannelError` only fires when you actually construct or connect a Slack
channel without the package installed.

Config keys:

* ``bot_token``  — ``xoxb-…`` Web API token (required for :meth:`send`).
* ``app_token``  — ``xapp-…`` Socket Mode token (required for inbound listening).
* ``channel``    — default channel id / name to post to (e.g. ``#general``).
"""

from __future__ import annotations

from typing import Any

from eidetic_os.channels.base import Channel, ChannelError, Handler


def _require_slack_sdk() -> Any:
    """Import ``slack_sdk`` or raise a clear, actionable :class:`ChannelError`."""
    try:
        import slack_sdk  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via the guard test
        raise ChannelError(
            "the Slack channel needs the 'slack-sdk' package — "
            "install it with: pip install 'eidetic-os[slack]'"
        ) from exc
    return slack_sdk


class SlackChannel(Channel):
    """A Slack adapter: posts with the Web API, listens over Socket Mode."""

    name = "slack"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.bot_token = self.config.get("bot_token", "")
        self.app_token = self.config.get("app_token", "")
        self.channel = self.config.get("channel", "")
        self._client: Any | None = None
        self._socket: Any | None = None

    async def connect(self) -> None:
        """Build the Web API client (and a Socket Mode client if a handler is set)."""
        slack_sdk = _require_slack_sdk()
        if not self.bot_token:
            raise ChannelError("slack: 'bot_token' is required (xoxb-…)")
        self._client = slack_sdk.WebClient(token=self.bot_token)
        if self._handler is not None and self.app_token:
            self._start_socket_mode(slack_sdk)

    def _start_socket_mode(self, slack_sdk: Any) -> None:  # pragma: no cover - needs network
        from slack_sdk.socket_mode import SocketModeClient  # type: ignore
        from slack_sdk.socket_mode.request import SocketModeRequest  # type: ignore
        from slack_sdk.socket_mode.response import SocketModeResponse  # type: ignore

        socket = SocketModeClient(app_token=self.app_token, web_client=self._client)

        def _on_request(client: Any, req: SocketModeRequest) -> None:
            client.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id)
            )
            if req.type != "events_api":
                return
            event = req.payload.get("event", {})
            if event.get("type") == "message" and "bot_id" not in event:
                reply = self.reply_sync(str(event.get("text", "")))
                if reply:
                    client.web_client.chat_postMessage(
                        channel=event.get("channel", self.channel), text=reply
                    )

        socket.socket_mode_request_listeners.append(_on_request)
        socket.connect()
        self._socket = socket

    async def send(self, message: str) -> None:
        """Post ``message`` to the configured channel via ``chat.postMessage``."""
        if self._client is None:
            raise ChannelError("slack: call connect() before send()")
        if not self.channel:
            raise ChannelError("slack: 'channel' is required to send")
        try:  # pragma: no cover - needs the Slack API
            self._client.chat_postMessage(channel=self.channel, text=message)
        except Exception as exc:  # noqa: BLE001 - surface any SlackApiError uniformly
            raise ChannelError(f"slack send failed: {exc}") from exc

    async def on_message(self, handler: Handler) -> None:
        self._handler = handler

    async def disconnect(self) -> None:
        if self._socket is not None:  # pragma: no cover - needs network
            self._socket.disconnect()
            self._socket = None
        self._client = None


def make_slack_channel(config: dict[str, Any]) -> Channel:
    """Factory registered under ``slack`` (see :mod:`eidetic_os.channels`)."""
    return SlackChannel(config)
