# -*- coding: utf-8 -*-
"""Method D: state-feedback adaptive search.

The controller's decision is converted into actual generator parameters.
No LLM text is used as a substitute for candidate generation.
"""

from __future__ import annotations

import math

from core.schemas import AgentDecision, CandidatePlan, OptimizationState, Strategy
from optimizers.base import BaseSearch, SearchConfig


class AdaptiveSearch(BaseSearch):
    name = "adaptive"

    def __init__(self, scenario, *, seed: int = 7):
        super().__init__(scenario, seed=seed)
        self.config = SearchConfig()
        self.last_decision: AgentDecision | None = None

    def apply_decision(self, decision: AgentDecision) -> SearchConfig:
        step = decision.search_step if decision.search_step is not None else self.config.search_step
        exploration = (decision.exploration_ratio if decision.exploration_ratio is not None
                       else self.config.exploration_ratio)
        count = decision.candidate_count if decision.candidate_count is not None else self.config.candidate_count
        self.config = SearchConfig(
            search_step=min(0.5, max(0.01, float(step))),
            exploration_ratio=min(1.0, max(0.0, float(exploration))),
            candidate_count=max(1, min(8, int(count))),
            target_variables=[v for v in (decision.target_variables or []) if v in self.bounds],
            optimizer_type=self.name,
        )
        self.last_decision = decision
        return self.config

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        cfg = self.apply_decision(decision)
        base = state.best_candidate or state.current_candidate
        strategy = decision.action
        if not isinstance(strategy, Strategy):
            strategy = Strategy(str(strategy))
        if base is None:
            return [self.sample_random(rng, state.iteration + 1, strategy.value)]

        if strategy in (Strategy.EXPLORE, Strategy.DIVERSIFY):
            return [self.sample_random(rng, state.iteration + 1, strategy.value)
                    for _ in range(cfg.candidate_count)]

        n_random = int(round(cfg.candidate_count * cfg.exploration_ratio))
        if strategy in (Strategy.EXPLOIT, Strategy.LOCAL_REFINE):
            n_random = min(n_random, max(0, cfg.candidate_count - 1))
        if strategy in (Strategy.REPAIR, Strategy.CONSTRAINT_FOCUSED):
            n_random = 0
        n_local = max(0, cfg.candidate_count - n_random)
        proposals: list[CandidatePlan] = []
        for _ in range(n_random):
            proposals.append(self.sample_random(rng, state.iteration + 1, f"{strategy.value}-explore"))
        for _ in range(n_local):
            proposals.append(self.sample_local(
                base, rng, state.iteration + 1, cfg.search_step, strategy.value,
                variables=cfg.target_variables or None,
            ))
        if not proposals:
            proposals.append(self.sample_local(base, rng, state.iteration + 1, cfg.search_step, strategy.value))
        return proposals
