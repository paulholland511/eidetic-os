"""Tests for eidetic_os.memory_scoring — time-weighted relevance scoring (#27).

The forgetting curve ``P(M) = e^(-λt)·(1 + βf)`` is exercised with known inputs
and an injected ``now`` so every assertion is deterministic and offline. The
integration tests drive a real :class:`~eidetic_os.facts.FactStore` (no embedder)
to confirm the column migration, persistence, deactivation, and the hot/stale
queries all hang together.
"""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
from pathlib import Path

import pytest

from eidetic_os import config, facts
from eidetic_os.memory_scoring import DecaySummary, MemoryScorer


@pytest.fixture()
def store(tmp_path: Path) -> facts.FactStore:
    s = facts.FactStore(tmp_path / "facts.db")  # offline: no embedder needed
    yield s
    s.close()


@pytest.fixture()
def scorer(store: facts.FactStore) -> MemoryScorer:
    # Pin parameters so tests don't depend on a config file on disk.
    return MemoryScorer(
        store,
        decay_lambda=0.01,
        reinforcement_beta=0.5,
        deactivation_threshold=0.05,
    )


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── The formula ────────────────────────────────────────────────────────────────
class TestScoreFormula:
    def test_fresh_zero_access_scores_one(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("a fact")
        fact = store.get(fid)
        # t=0, f=0 → e^0 · (1 + 0) = 1.0
        assert scorer.score(fact, now=_now()) == pytest.approx(1.0)

    def test_reinforcement_raises_fresh_score(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("hot fact")
        for _ in range(4):
            store.touch(fid)
        fact = store.get(fid)
        # t≈0, f=4 → 1 · (1 + 0.5·4) = 3.0
        assert scorer.score(fact, now=_now()) == pytest.approx(3.0, abs=1e-3)

    def test_decay_with_known_inputs(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("aging fact")
        fact = store.get(fid)
        future = _parse(fact.last_accessed) + dt.timedelta(days=10)
        # t=10, f=0, λ=0.01 → e^(-0.1)·1
        assert scorer.score(fact, now=future) == pytest.approx(math.exp(-0.1), abs=1e-4)

    def test_decay_and_reinforcement_combine(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("aging hot fact")
        store.touch(fid)
        store.touch(fid)
        fact = store.get(fid)
        future = _parse(fact.last_accessed) + dt.timedelta(days=20)
        # t=20, f=2 → e^(-0.2)·(1 + 0.5·2) = e^(-0.2)·2
        expected = math.exp(-0.2) * 2.0
        assert scorer.score(fact, now=future) == pytest.approx(expected, abs=1e-4)

    def test_clock_skew_never_exceeds_max(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("future fact")
        fact = store.get(fid)
        past = _parse(fact.last_accessed) - dt.timedelta(days=5)  # now < last_accessed
        # Negative age is clamped to 0 → score is the just-accessed value, not >1.
        assert scorer.score(fact, now=past) == pytest.approx(1.0)


# ── decay_all ───────────────────────────────────────────────────────────────────
class TestDecayAll:
    def test_persists_relevance(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("a fact")
        future = _parse(store.get(fid).last_accessed) + dt.timedelta(days=10)
        summary = scorer.decay_all(now=future)
        assert isinstance(summary, DecaySummary)
        assert summary.scored == 1
        assert store.get(fid).relevance_score == pytest.approx(math.exp(-0.1), abs=1e-4)

    def test_deactivates_below_threshold(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("ancient fact")
        # 500 days, f=0 → e^(-5) ≈ 0.0067 < 0.05 → forgotten.
        future = _parse(store.get(fid).last_accessed) + dt.timedelta(days=500)
        summary = scorer.decay_all(now=future)
        assert summary.deactivated == 1
        assert store.get(fid).active is False

    def test_hot_fact_survives_decay(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("well-loved fact")
        for _ in range(20):
            store.touch(fid)
        future = _parse(store.get(fid).last_accessed) + dt.timedelta(days=200)
        scorer.decay_all(now=future)
        # e^(-2)·(1 + 0.5·20) = e^(-2)·11 ≈ 1.49 — still well above threshold.
        assert store.get(fid).active is True
        assert store.get(fid).relevance_score == pytest.approx(math.exp(-2) * 11, abs=1e-3)

    def test_idempotent_for_fixed_now(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("a fact")
        future = _parse(store.get(fid).last_accessed) + dt.timedelta(days=10)
        scorer.decay_all(now=future)
        first = store.get(fid).relevance_score
        scorer.decay_all(now=future)
        assert store.get(fid).relevance_score == pytest.approx(first)

    def test_empty_store_summary(self, scorer: MemoryScorer) -> None:
        summary = scorer.decay_all(now=_now())
        assert summary == DecaySummary(0, 0, None, None)

    def test_ignores_inactive(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("x")
        store.deactivate(fid)
        summary = scorer.decay_all(now=_now())
        assert summary.scored == 0


# ── boost ────────────────────────────────────────────────────────────────────────
class TestBoost:
    def test_boost_resets_timer_and_rescores(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("a fact")
        # Decay it into the cold first.
        future = _parse(store.get(fid).last_accessed) + dt.timedelta(days=50)
        scorer.decay_all(now=future)
        assert store.get(fid).relevance_score < 1.0
        # Boost touches (access_count 0→1, last_accessed=now) and rescores at t≈0.
        new = scorer.boost(fid)
        fact = store.get(fid)
        assert fact.access_count == 1
        # t≈0, f=1 → 1·(1 + 0.5) = 1.5
        assert new == pytest.approx(1.5, abs=1e-2)
        assert fact.relevance_score == pytest.approx(new)

    def test_boost_unknown_id_returns_none(self, scorer: MemoryScorer) -> None:
        assert scorer.boost(9999) is None


# ── hot / stale queries ──────────────────────────────────────────────────────────
class TestHotStale:
    def test_hot_orders_by_relevance(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        cold = store.add_fact("cold")
        hot = store.add_fact("hot")
        for _ in range(10):
            store.touch(hot)
        scorer.decay_all(now=_now())
        ranked = scorer.get_hot(limit=10)
        assert ranked[0].id == hot
        assert {cold, hot} == {f.id for f in ranked}

    def test_stale_returns_below_threshold(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        fid = store.add_fact("aging fact")
        # ~115 days → e^(-1.15) ≈ 0.317; below 0.5 but above the 0.05 deactivation floor.
        future = _parse(store.get(fid).last_accessed) + dt.timedelta(days=115)
        scorer.decay_all(now=future)
        assert [f.id for f in scorer.get_stale(threshold=0.5)] == [fid]
        assert scorer.get_stale(threshold=0.1) == []


# ── FactStore migration + context ordering ──────────────────────────────────────
class TestStoreIntegration:
    def test_relevance_column_defaults_to_one(self, store: facts.FactStore) -> None:
        fid = store.add_fact("a fact")
        assert store.get(fid).relevance_score == pytest.approx(1.0)

    def test_migration_adds_column_to_legacy_db(self, tmp_path: Path) -> None:
        # Build a "legacy" facts table with no relevance_score column.
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE facts (
                id INTEGER PRIMARY KEY, fact TEXT NOT NULL, source TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL, last_accessed TIMESTAMP NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0, confidence REAL NOT NULL DEFAULT 0.6,
                category TEXT NOT NULL DEFAULT 'other', embedding BLOB,
                active INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO facts(fact, created_at, last_accessed)
            VALUES ('old fact', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            """
        )
        conn.commit()
        conn.close()
        # Opening through FactStore must transparently add the column.
        s = facts.FactStore(db)
        try:
            assert s.get(1).relevance_score == pytest.approx(1.0)
        finally:
            s.close()

    def test_context_prefers_higher_relevance(
        self, store: facts.FactStore, scorer: MemoryScorer
    ) -> None:
        low = store.add_fact("low relevance", confidence=0.9)
        high = store.add_fact("high relevance", confidence=0.1)
        store.set_relevance(low, 0.2)
        store.set_relevance(high, 0.9)
        ctx = store.get_facts_for_context(limit=10)
        # relevance_score wins over the confidence·access salience proxy.
        assert ctx[0].id == high


# ── Config integration ──────────────────────────────────────────────────────────
class TestConfigParams:
    def test_reads_params_from_config(
        self, tmp_path: Path, store: facts.FactStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "memory:\n  decay_lambda: 0.02\n  reinforcement_beta: 1.0\n"
            "  deactivation_threshold: 0.2\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("EIDETIC_CONFIG_PATH", str(cfg))
        scorer = MemoryScorer(store)
        assert scorer.decay_lambda == pytest.approx(0.02)
        assert scorer.reinforcement_beta == pytest.approx(1.0)
        assert scorer.deactivation_threshold == pytest.approx(0.2)

    def test_explicit_args_override_config(
        self, tmp_path: Path, store: facts.FactStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  decay_lambda: 0.02\n", encoding="utf-8")
        monkeypatch.setenv("EIDETIC_CONFIG_PATH", str(cfg))
        scorer = MemoryScorer(store, decay_lambda=0.5)
        assert scorer.decay_lambda == pytest.approx(0.5)

    def test_defaults_when_no_config(
        self, store: facts.FactStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EIDETIC_CONFIG_PATH", "/nonexistent/config.yaml")
        scorer = MemoryScorer(store)
        assert scorer.decay_lambda == pytest.approx(config.DEFAULT_MEMORY["decay_lambda"])


def _parse(iso: str) -> dt.datetime:
    """Parse a stored ISO timestamp back to an aware datetime (test helper)."""
    return facts._parse_iso(iso)
