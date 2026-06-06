"""Time-weighted relevance scoring for the fact store (Feature #27).

The fact store (:mod:`eidetic_os.facts`) already deduplicates and decays
*confidence*. This module adds a second, orthogonal signal — **relevance** —
that captures how live a fact is *right now*, combining recency of access with
how often it has been reinforced.

The model is a forgetting curve with reinforcement:

    P(M) = e^(-λt) · (1 + βf)

where

* ``t`` — days since the fact was last accessed,
* ``f`` — how many times it has been accessed (the ``access_count``),
* ``λ`` — the decay rate (``decay_lambda``; 0.01/day ≈ a 69-day half-life),
* ``β`` — the reinforcement coefficient (``reinforcement_beta``).

A fact accessed moments ago scores ``1 + βf`` and decays exponentially as it is
left untouched; every access both resets ``t`` to zero and raises ``f``, so
frequently-used facts stay hot far longer than the bare decay curve would allow.
Facts that fall below ``deactivation_threshold`` are forgotten (deactivated).

The three parameters are read from ``.eidetic/config.yaml`` (the ``memory:``
section) via :func:`eidetic_os.config.memory_params`, falling back to the
documented defaults, so they are tunable without touching code. The
:class:`~eidetic_os.sleeptime.ConsolidationDaemon` calls :meth:`decay_all` on
every pass, keeping the scores fresh as a background side effect of memory
consolidation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from eidetic_os import config
from eidetic_os.facts import FactStore, StoredFact, _parse_iso

_SECONDS_PER_DAY: Final = 86400.0


@dataclass(frozen=True)
class DecaySummary:
    """The outcome of a :meth:`MemoryScorer.decay_all` pass.

    ``scored`` is how many active facts were rescored; ``deactivated`` is how
    many of those fell below the deactivation threshold and were forgotten;
    ``hottest``/``coldest`` are the extreme relevance scores observed (``None``
    when the store held no active facts).
    """

    scored: int
    deactivated: int
    hottest: float | None
    coldest: float | None


class MemoryScorer:
    """Compute and persist time-weighted relevance for stored facts.

    Construct with a :class:`~eidetic_os.facts.FactStore`; the parameters default
    to the values in ``.eidetic/config.yaml`` but can be overridden explicitly
    (the CLI and tests do this). All methods are synchronous and offline — the
    formula needs only the columns already on each row.
    """

    def __init__(
        self,
        store: FactStore,
        *,
        decay_lambda: float | None = None,
        reinforcement_beta: float | None = None,
        deactivation_threshold: float | None = None,
    ) -> None:
        params = config.memory_params()
        self.store = store
        self.decay_lambda = (
            params["decay_lambda"] if decay_lambda is None else decay_lambda
        )
        self.reinforcement_beta = (
            params["reinforcement_beta"]
            if reinforcement_beta is None
            else reinforcement_beta
        )
        self.deactivation_threshold = (
            params["deactivation_threshold"]
            if deactivation_threshold is None
            else deactivation_threshold
        )

    # ── the formula ─────────────────────────────────────────────────────────────
    def score(self, fact: StoredFact, *, now: datetime | None = None) -> float:
        """Relevance ``P(M) = e^(-λt)·(1 + βf)`` for ``fact`` at ``now``.

        ``t`` is days (fractional) since the fact was last accessed, clamped at
        zero so a clock skew can't push relevance above the just-accessed
        maximum. A row with an unparseable ``last_accessed`` is treated as
        just-accessed (``t = 0``) rather than infinitely stale.
        """
        reference = now or datetime.now(timezone.utc)
        accessed = _parse_iso(fact.last_accessed)
        if accessed is None:
            age_days = 0.0
        else:
            age_days = max(0.0, (reference - accessed).total_seconds() / _SECONDS_PER_DAY)
        decay = math.exp(-self.decay_lambda * age_days)
        reinforcement = 1.0 + self.reinforcement_beta * fact.access_count
        return decay * reinforcement

    # ── batch maintenance ───────────────────────────────────────────────────────
    def decay_all(self, *, now: datetime | None = None) -> DecaySummary:
        """Rescore every active fact, deactivating those below the threshold.

        Idempotent for a fixed ``now``: each pass recomputes relevance from the
        immutable inputs (last access, access count) rather than mutating a
        running score, so running it twice in a row yields the same state.
        Returns a :class:`DecaySummary`. ``now`` is injectable for testing.
        """
        reference = now or datetime.now(timezone.utc)
        facts = self.store.active_facts()
        deactivated = 0
        hottest: float | None = None
        coldest: float | None = None
        for fact in facts:
            relevance = self.score(fact, now=reference)
            below = relevance < self.deactivation_threshold
            self.store.set_relevance(fact.id, relevance, deactivate=below)
            if below:
                deactivated += 1
            hottest = relevance if hottest is None else max(hottest, relevance)
            coldest = relevance if coldest is None else min(coldest, relevance)
        return DecaySummary(
            scored=len(facts),
            deactivated=deactivated,
            hottest=hottest,
            coldest=coldest,
        )

    def boost(self, fact_id: int, *, now: datetime | None = None) -> float | None:
        """Manually reinforce a fact: reset its decay timer and rescore it.

        Records an access (bumping ``access_count`` and resetting
        ``last_accessed`` to now) and recomputes relevance from the fresh row, so
        a boosted fact jumps to ``1 + βf`` with ``t = 0``. Returns the new
        relevance, or ``None`` if no fact has that id.
        """
        if self.store.get(fact_id) is None:
            return None
        self.store.touch(fact_id)
        fact = self.store.get(fact_id)
        if fact is None:  # pragma: no cover - touched row cannot vanish
            return None
        relevance = self.score(fact, now=now)
        self.store.set_relevance(fact_id, relevance)
        return relevance

    # ── queries ─────────────────────────────────────────────────────────────────
    def get_stale(self, threshold: float = 0.1, *, limit: int = 100) -> list[StoredFact]:
        """Active facts whose relevance has fallen below ``threshold`` (coldest first).

        These are the facts approaching deactivation — useful for review before a
        decay pass forgets them.
        """
        return self.store.stale_facts(threshold, limit=limit)

    def get_hot(self, limit: int = 20) -> list[StoredFact]:
        """The ``limit`` most relevant active facts, hottest first."""
        return self.store.hot_facts(limit=limit)
