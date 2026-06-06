"""Tests for eidetic_os.channels — the channel adapter framework (#26).

All tests run offline. The webhook adapter is exercised end-to-end against its
own real (loopback) HTTP server; message routing is tested with an injected fact
search; the Slack/Telegram adapters are tested for their config wiring and their
missing-dependency guards (the SDKs are not installed in CI).
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

import pytest

from eidetic_os import channels
from eidetic_os.channels import Channel, ChannelError, make_rag_router
from eidetic_os.channels.base import make_rag_router as base_router
from eidetic_os.channels.slack import SlackChannel
from eidetic_os.channels.telegram import TelegramChannel
from eidetic_os.channels.webhook import WebhookChannel


def _run(coro):
    return asyncio.run(coro)


# ── ABC contract ─────────────────────────────────────────────────────────────────
class TestContract:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            Channel()  # type: ignore[abstract]

    def test_concrete_channels_implement_contract(self) -> None:
        for cls in (WebhookChannel, SlackChannel, TelegramChannel):
            ch = cls({})
            for method in ("connect", "send", "on_message", "disconnect"):
                assert callable(getattr(ch, method))
            assert isinstance(ch.name, str)

    def test_reply_with_no_handler_is_empty(self) -> None:
        ch = WebhookChannel({})
        assert _run(ch.reply("hello")) == ""

    def test_reply_runs_sync_handler(self) -> None:
        ch = WebhookChannel({})
        _run(ch.on_message(lambda text: f"echo:{text}"))
        assert _run(ch.reply("hi")) == "echo:hi"

    def test_reply_runs_async_handler(self) -> None:
        ch = WebhookChannel({})

        async def handler(text: str) -> str:
            return f"async:{text}"

        _run(ch.on_message(handler))
        assert _run(ch.reply("hi")) == "async:hi"


# ── Message routing through (mocked) memory ──────────────────────────────────────
class TestRouter:
    def test_routes_query_to_facts(self) -> None:
        def fake_search(query: str, limit: int):
            return [("technical", 0.91, "the bot uses Kelly sizing")]

        router = make_rag_router(fact_search=fake_search)
        out = router("how does the bot size bets?")
        assert "Kelly sizing" in out
        assert "technical" in out

    def test_empty_query_returns_greeting(self) -> None:
        router = make_rag_router(fact_search=lambda q, n: [])
        assert "ask me" in router("   ").lower()

    def test_no_hits_message(self) -> None:
        router = make_rag_router(fact_search=lambda q, n: [])
        assert "No matching facts" in router("obscure question")

    def test_search_failure_is_caught(self) -> None:
        def boom(query: str, limit: int):
            raise RuntimeError("backend down")

        router = make_rag_router(fact_search=boom)
        assert "search failed" in router("anything")

    def test_exported_alias_is_same(self) -> None:
        assert make_rag_router is base_router


# ── Webhook adapter (end-to-end, real loopback server) ───────────────────────────
class TestWebhook:
    def test_inbound_post_is_routed(self) -> None:
        ch = WebhookChannel({"host": "127.0.0.1", "port": 0})
        _run(ch.on_message(make_rag_router(
            fact_search=lambda q, n: [("preference", 0.8, "Paul prefers uv")]
        )))
        _run(ch.connect())
        try:
            port = ch.bound_port
            assert port is not None
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/",
                data=json.dumps({"message": "package manager?"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read())
            assert "Paul prefers uv" in body["reply"]
        finally:
            _run(ch.disconnect())

    def test_invalid_json_returns_400(self) -> None:
        ch = WebhookChannel({"port": 0})
        _run(ch.connect())
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{ch.bound_port}/",
                data=b"not json",
                method="POST",
            )
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(req, timeout=5)
            assert exc.value.code == 400
        finally:
            _run(ch.disconnect())

    def test_send_without_outbound_records_locally(self) -> None:
        ch = WebhookChannel({})
        _run(ch.send("hello world"))
        assert ch.last_sent == "hello world"

    def test_disconnect_is_safe_when_never_connected(self) -> None:
        ch = WebhookChannel({})
        _run(ch.disconnect())  # must not raise

    def test_connect_is_idempotent(self) -> None:
        ch = WebhookChannel({"port": 0})
        _run(ch.connect())
        first = ch.bound_port
        _run(ch.connect())  # second call is a no-op
        try:
            assert ch.bound_port == first
        finally:
            _run(ch.disconnect())


# ── Registry + config loading ────────────────────────────────────────────────────
class TestRegistry:
    def test_available_includes_builtins(self) -> None:
        available = channels.available_channels()
        assert {"webhook", "slack", "telegram"} <= set(available)

    def test_create_webhook(self) -> None:
        ch = channels.create_channel("webhook", {"port": 0})
        assert isinstance(ch, WebhookChannel)
        assert ch.name == "webhook"

    def test_create_unknown_raises(self) -> None:
        with pytest.raises(ChannelError):
            channels.create_channel("carrier-pigeon", {})

    def test_register_custom_factory(self) -> None:
        ch = WebhookChannel({})
        channels.register("custom-test", lambda cfg: ch)
        try:
            assert channels.create_channel("custom-test", {}) is ch
        finally:
            channels._REGISTRY.pop("custom-test", None)

    def test_load_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "channels.yaml"
        cfg.write_text(
            "webhook:\n  port: 9000\nslack:\n  bot_token: xoxb-test\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("EIDETIC_CHANNELS_PATH", str(cfg))
        loaded = channels.load_channels_config()
        assert loaded["webhook"]["port"] == 9000
        assert loaded["slack"]["bot_token"] == "xoxb-test"

    def test_missing_config_is_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EIDETIC_CHANNELS_PATH", str(tmp_path / "nope.yaml"))
        assert channels.load_channels_config() == {}

    def test_create_uses_config_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "channels.yaml"
        cfg.write_text("webhook:\n  port: 0\n  path: /hook\n", encoding="utf-8")
        monkeypatch.setenv("EIDETIC_CHANNELS_PATH", str(cfg))
        ch = channels.create_channel("webhook")  # no explicit config → reads file
        assert isinstance(ch, WebhookChannel)
        assert ch.path == "/hook"


# ── Optional-dependency guards ───────────────────────────────────────────────────
class TestOptionalDeps:
    def test_slack_config_wiring(self) -> None:
        ch = SlackChannel({"bot_token": "xoxb-x", "channel": "#general"})
        assert ch.bot_token == "xoxb-x"
        assert ch.channel == "#general"

    def test_telegram_config_wiring(self) -> None:
        ch = TelegramChannel({"bot_token": "123:abc", "chat_id": "42"})
        assert ch.bot_token == "123:abc"
        assert ch.chat_id == "42"

    def test_slack_connect_without_sdk_raises_channelerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate slack_sdk being absent.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "slack_sdk" or name.startswith("slack_sdk."):
                raise ImportError("no slack_sdk")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        ch = SlackChannel({"bot_token": "xoxb-x"})
        with pytest.raises(ChannelError, match="slack-sdk"):
            _run(ch.connect())

    def test_telegram_connect_without_ptb_raises_channelerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "telegram" or name.startswith("telegram."):
                raise ImportError("no telegram")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        ch = TelegramChannel({"bot_token": "123:abc"})
        with pytest.raises(ChannelError, match="python-telegram-bot"):
            _run(ch.connect())

    def test_send_before_connect_raises(self) -> None:
        with pytest.raises(ChannelError, match="connect"):
            _run(SlackChannel({"bot_token": "x", "channel": "#c"}).send("hi"))
        with pytest.raises(ChannelError, match="connect"):
            _run(TelegramChannel({"bot_token": "x", "chat_id": "1"}).send("hi"))
