# Atlas OS — Trading SDK (optional module)

A small, dependency-light multi-agent framework for generating trading
*research briefings* from a local LLM. Four deterministic / LLM analyst agents
(technical, fundamentals, sentiment, news) produce per-asset signals, and an
optional Portfolio Manager step synthesises them into a final recommendation.

> ⚠️ **Not financial advice.** This module is a research and automation
> template. It does not place trades by itself, and nothing it outputs is a
> recommendation to buy or sell anything. The asset lists shipped here are
> illustrative defaults. You are solely responsible for any use. Markets are
> risky; you can lose money.

## What's here

| File | Purpose |
|---|---|
| `core.py` | Base classes (`Tool`, `Agent`, `Orchestrator`) + model router for OpenAI-compatible and Anthropic endpoints. |
| `config.py.example` | All constants, endpoints, and asset lists. Copy to `config.py`. |
| `agents/` | The analyst agents (`technical`, `fundamentals`, `sentiment`, `news`, `portfolio`). |
| `freqtrade_bridge.py` | Optional: parse a saved briefing and emit a `signals.json` for a [Freqtrade](https://www.freqtrade.io/) strategy to consume. |
| `freqtrade_bridge.config.json` | Bridge configuration (paths, PM provider, ticker→pair map). |

The end-to-end briefing generator that writes a markdown note into your vault is
`../scripts/trading_briefing.py`.

## Setup

```bash
# 1. Configure
cp config.py.example config.py        # then edit, or just rely on env vars

# 2. Point at your local LLM (OpenAI-compatible: LM Studio, Ollama, etc.)
export LM_STUDIO_HOST=localhost
export LM_STUDIO_PORT=5555
export LM_STUDIO_MODEL=local-model

# 3. (Optional) enable the cloud Portfolio Manager step
export ANTHROPIC_API_KEY=sk-ant-...   # never commit this

# 4. Dependencies
pip install requests yfinance
```

## Architecture

```
  [Local LLM]  fundamentals + sentiment + news + technical  → briefing.md
                                                                  │
                                                                  ▼
  [Portfolio Manager]  debate → final signal + confidence + reasoning
        (local LLM by default, Anthropic optional)                │
                                                                  ▼
                                                        signals.json
                                                                  │
                                                                  ▼
                                                     Freqtrade strategy
```

## Privacy

By default everything runs against your **local** LLM — no market data, notes,
or positions leave your machine. The cloud Portfolio Manager step is strictly
opt-in and only sends the (already anonymous) analyst votes. See
[`../SECURITY.md`](../SECURITY.md) and
[`../docs/DATA-CLASSIFICATION.md`](../docs/DATA-CLASSIFICATION.md).
