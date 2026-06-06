"""Telegram channel adapter — outbound + inbound via the Bot API.

Needs the optional ``python-telegram-bot`` dependency
(``pip install 'eidetic-os[telegram]'``). The import is lazy and guarded, so
listing channels never requires it; the clear :class:`ChannelError` only fires
when you construct or connect a Telegram channel without the package installed.

Config keys:

* ``bot_token`` — the BotFather token (required).
* ``chat_id``   — default chat id to post to with :meth:`send`.
"""

from __future__ import annotations

from typing import Any

from eidetic_os.channels.base import Channel, ChannelError, Handler


def _require_ptb() -> Any:
    """Import ``telegram`` (python-telegram-bot) or raise a clear :class:`ChannelError`."""
    try:
        import telegram  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via the guard test
        raise ChannelError(
            "the Telegram channel needs the 'python-telegram-bot' package — "
            "install it with: pip install 'eidetic-os[telegram]'"
        ) from exc
    return telegram


class TelegramChannel(Channel):
    """A Telegram adapter: sends and (optionally) long-polls for messages."""

    name = "telegram"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.bot_token = self.config.get("bot_token", "")
        self.chat_id = self.config.get("chat_id", "")
        self._bot: Any | None = None
        self._app: Any | None = None

    async def connect(self) -> None:
        """Build the Bot client (and a polling application when a handler is set)."""
        telegram = _require_ptb()
        if not self.bot_token:
            raise ChannelError("telegram: 'bot_token' is required")
        self._bot = telegram.Bot(token=self.bot_token)
        if self._handler is not None:
            self._start_polling()

    def _start_polling(self) -> None:  # pragma: no cover - needs network
        from telegram.ext import (  # type: ignore
            ApplicationBuilder,
            ContextTypes,
            MessageHandler,
            filters,
        )

        app = ApplicationBuilder().token(self.bot_token).build()

        async def _on_message(update: Any, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
            if update.message is None or not update.message.text:
                return
            reply = await self.reply(update.message.text)
            if reply:
                await update.message.reply_text(reply)

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))
        app.run_polling(close_loop=False)
        self._app = app

    async def send(self, message: str) -> None:
        """Send ``message`` to the configured ``chat_id``."""
        if self._bot is None:
            raise ChannelError("telegram: call connect() before send()")
        if not self.chat_id:
            raise ChannelError("telegram: 'chat_id' is required to send")
        try:  # pragma: no cover - needs the Telegram API
            await self._bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as exc:  # noqa: BLE001 - surface any TelegramError uniformly
            raise ChannelError(f"telegram send failed: {exc}") from exc

    async def on_message(self, handler: Handler) -> None:
        self._handler = handler

    async def disconnect(self) -> None:
        if self._app is not None:  # pragma: no cover - needs network
            await self._app.stop()
            self._app = None
        self._bot = None


def make_telegram_channel(config: dict[str, Any]) -> Channel:
    """Factory registered under ``telegram`` (see :mod:`eidetic_os.channels`)."""
    return TelegramChannel(config)
