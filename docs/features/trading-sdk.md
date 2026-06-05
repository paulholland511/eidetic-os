# Feature: Trading Research SDK (optional)

**Source:** [`trading/`](../../trading/README.md),
[`scripts/trading_briefing.py`](../../scripts/trading_briefing.py) ·
**Install:** `eidetic-os[trading]`

> ⚠️ **Not financial advice.** This module is a research/automation template. It
> does **not** place trades, and nothing it outputs is a recommendation to buy or
> sell anything. The asset lists are illustrative. You are solely responsible for
> any use; markets are risky and you can lose money.

A dependency-light, multi-agent framework that produces **trading research
briefings** from a local LLM and writes them into your vault (so RAG indexes
them). Optionally, a bridge turns a briefing into machine-readable signals for a
[Freqtrade](https://www.freqtrade.io/) strategy.

---

## Three pieces (and how they relate)

Eidetic OS's trading code has three parts that share *conventions* (signal format,
vault location) but not all imports:

1. **The analyst SDK** — [`trading/core.py`](../../trading/core.py) +
   [`trading/agents/*`](../../trading/agents) — base classes, a model router,
   four analyst agents, and a local Portfolio Manager.
2. **The briefing generator** —
   [`scripts/trading_briefing.py`](../../scripts/trading_briefing.py) — drives the
   **third-party `tradingagents` package** (installed at `TRADING_AGENTS_PATH`)
   to write a briefing note. It does *not* import the SDK in (1).
3. **The Freqtrade bridge** —
   [`trading/freqtrade_bridge.py`](../../trading/freqtrade_bridge.py) — parses a
   briefing, runs its **own** LLM Portfolio-Manager step, and emits
   `signals.json`.

> There are therefore **two "Portfolio Managers"**: the local arithmetic one in
> `agents/portfolio.py`, and the LLM-debate one in `freqtrade_bridge.py`. Only the
> bridge's PM has the cloud (Anthropic) opt-in.

---

## 1. The analyst SDK

### Core (`core.py`)

- **`ModelConfig`** (frozen): `endpoint`, `model`, `api_key`, `provider`
  (`"openai_compatible"` or `"anthropic"`).
- **Model router** — `call_model(config, system, user, tools=None)` dispatches by
  provider:
  - *openai_compatible* → `POST {endpoint}/v1/chat/completions`
    (`temperature 0.3`, `max_tokens 2000`); bearer header only if a key is set.
  - *anthropic* → `POST {endpoint}/v1/messages` with `x-api-key` +
    `anthropic-version`.
  - Both retry on connection errors and raise `ModelUnavailable` on failure.
  - `get_lm_studio_config()` and `get_anthropic_config()` build the two configs
    from env vars. **The provider choice is per-agent** (which factory it uses) —
    there's no single global switch in `core.py`.
- **`Tool`** (ABC) — structured tool interface (no concrete tools ship; agents
  run with `tools=[]`).
- **`Agent`** (ABC) — each returns a standardised dict via `_make_output(…)`:
  `agent`, `ticker`, `recommendation` (`BUY`/`SELL`/`HOLD`), `confidence`
  (0–1, clamped), `reasoning`, `targets`, `timestamp`, plus extras.
- **`Orchestrator`** — runs agents concurrently via a thread pool
  (`dispatch(agents, context, timeout_per_agent=60)`); a failed agent yields
  `{agent, error, status:"failed"}` instead of crashing the run.

### The four analysts

| Agent | Type | What it does | Notable output |
|---|---|---|---|
| **Technical** | Deterministic | Signal-counts pre-computed indicators (RSI 14, MACD, SMA 20/50, Bollinger Bands) into a net BUY/SELL score; derives support/resistance targets. *Indicators must be supplied in `context`.* | `buy_signals`, `sell_signals`, `rsi`, `macd_histogram` |
| **Fundamentals** | LLM-capable | Crypto: tries an LLM analysis (CoinGecko-style market-cap/rank/ATH/momentum data), falls back to deterministic. Stocks: pulls `yfinance` P/E, P/B, dividend, market cap → deterministic. | `market_cap`, `pe_ratio`, `analysis_mode` |
| **Sentiment** | Deterministic | **Contrarian** Fear & Greed logic (extreme fear → lean BUY, extreme greed → lean SELL) plus 7d/30d momentum modifiers. | `fear_greed_value`, `momentum_7d/30d` |
| **News** | Deterministic (Phase-1 placeholder) | No live news yet — uses 7-day price **volatility** as a catalyst proxy; deliberately low confidence. | `volatility_7d`, `catalyst_detected`, `phase:"1-placeholder"` |

Only **Fundamentals** can call the LLM (crypto path only); the rest are
deterministic. All emit the same `{recommendation, confidence, reasoning, …}`
shape.

### The Portfolio Manager (`agents/portfolio.py`) — local, deterministic

Synthesises the analyst votes into a final call by a **confidence-weighted vote**:
each agent's weight (`technical 0.35, fundamentals 0.25, sentiment 0.20, news 0.20`,
from `config.py`) is multiplied by its confidence; BUY/HOLD/SELL map to +1/0/−1;
the normalised score (≥0.3 → BUY, ≤−0.3 → SELL, else HOLD) is the recommendation.
Final confidence is the weighted average plus a **consensus bonus** (full
agreement +0.15, etc.), capped at 0.95. Failed agents are skipped and recorded.
No network calls — pure arithmetic.

---

## 2. The briefing generator (`scripts/trading_briefing.py`)

End-to-end:

1. Imports `TradingAgentsGraph` + `DEFAULT_CONFIG` from the **external**
   `tradingagents` package at `TRADING_AGENTS_PATH` (exits if not installed).
2. Builds a config pointing the package at your local LLM
   (`llm_provider="ollama"`, `backend_url=LM_STUDIO_URL`, models =
   `LM_STUDIO_MODEL`, `data_vendors` = `yfinance`).
3. Validates the endpoint (`check_lm_studio()`); `--dry-run` stops here.
4. For each ticker, `ta.propagate(ticker, date)` runs the analysis.
5. Writes a markdown briefing to
   **`$VAULT_PATH/wiki/sources/trading-briefing-<date>.md`** — frontmatter
   (`tags:[trading,briefing]`, `source:TradingAgents`, dates), a summary table
   `| Ticker | Status | Recommendation |`, per-ticker detail, and a config footer.

```bash
eidetic-os ships this as scripts/trading_briefing.py; run via:
python3 scripts/trading_briefing.py                 # all TRADING_TICKERS
python3 scripts/trading_briefing.py --ticker BTC-USD
python3 scripts/trading_briefing.py --date 2026-06-01
python3 scripts/trading_briefing.py --dry-run       # validate only
```

(The `daily-trading-report` skill wraps this on a schedule and emails the result.)

---

## 3. The Freqtrade bridge (`trading/freqtrade_bridge.py`)

Pipeline: find the latest `trading-briefing-YYYY-MM-DD.md` → parse per-asset
analyst votes (and a headline signal) → run a Portfolio-Manager step → write
`signals.json` for a Freqtrade strategy to consume.

- **PM step** (`run_portfolio_manager`): provider from `--provider` or the config.
  - `claude` → resolve an API key (`env:ANTHROPIC_API_KEY` →
    `~/.anthropic-api-key` → `~/.config/eidetic-os/.env`); use the `anthropic` SDK,
    else the `claude` CLI, else fall back to local.
  - `local` → `POST {endpoint}/v1/chat/completions` (OpenAI-compatible).
  - The model is asked to debate the votes and return strict JSON
    `{signal, confidence, reasoning}`; output is validated/clamped.
- **Freshness:** briefings older than `max_briefing_age_hours` (36) still produce
  signals but are marked `stale:true`.
- **Output:** `signals.json` (atomic write) keyed by Freqtrade **pair** (via the
  `ticker_to_pair` map; tickers without a mapping are dropped). Each signal:
  `signal`, `confidence`, `reasoning`, `source`, `ticker`, `votes`, `stale`.
- **Flags:** `--dry-run` (print, don't write), `--no-pm` (use the briefing
  headline directly), `--provider {claude,local}`.

Config: [`trading/freqtrade_bridge.config.json`](../../trading/freqtrade_bridge.config.json)
(`portfolio_manager.provider` default `local`; `claude`/`local` blocks;
`ticker_to_pair`; `paths`; `freshness`).

```
[Local LLM] technical + fundamentals + sentiment + news → briefing.md
                                                              │
                                                              ▼
[Portfolio Manager] debate → {signal, confidence}      → signals.json
  (local by default; Anthropic opt-in, bridge only)         │
                                                              ▼
                                                   Freqtrade strategy
```

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_PATH` | — (**required**) | where briefings are written |
| `LM_STUDIO_HOST` / `PORT` | `localhost` / `5555` | local chat endpoint |
| `LM_STUDIO_MODEL` | `local-model` | chat model |
| `LM_STUDIO_URL` | `…/v1` | used by `trading_briefing.py` (**needs `/v1`**) |
| `LM_STUDIO_ENDPOINT` | `…` (no `/v1`) | used by `trading/config.py` / `core.py` |
| `TRADING_AGENTS_PATH` | `~/Documents/TradingAgents` | the external package |
| `TRADING_TICKERS` | `BTC-USD,ETH-USD` | default watchlist |
| `ANTHROPIC_API_KEY` | — (opt-in) | bridge's cloud PM only |
| `ANTHROPIC_MODEL` | `claude-opus-4-6` | bridge's cloud PM model |

Copy `trading/config.py.example` → `config.py` to customise `ASSETS`,
`CRYPTO_COINGECKO_IDS`, `AGENT_WEIGHTS`, and timeouts.

## Privacy

Everything runs against your **local** LLM by default — no market data, notes, or
positions leave your machine. The bridge's cloud Portfolio Manager is strictly
opt-in and sends only the (already anonymous) analyst votes — never your notes or
positions. See [`docs/DATA-CLASSIFICATION.md`](../DATA-CLASSIFICATION.md).

See also: [`trading/README.md`](../../trading/README.md) ·
[skills-and-automation.md](skills-and-automation.md) ·
[`docs/SCRIPTS.md`](../SCRIPTS.md#trading_briefingpy)
