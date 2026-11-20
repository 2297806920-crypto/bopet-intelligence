# -*- coding: utf-8 -*-
"""Baseline C: fixed exploration/exploitation schedule (no state feedback)."""

from __future__ import annotations

from core.schemas import AgentDecision, CandidatePlan, OptimizationState
from optimizers.base import BaseSearch


class FixedScheduleSearch(BaseSearch):
    name = "fixed-schedule"

    def __init__(self, scenario, *, seed: int = 7, exploration_ratio: float = 0.30,
                 step: float = 0.12, candidate_count: int = 2):
        super().__init__(scenario, seed=seed)
        self.exploration_ratio = exploration_ratio
        self.step = step
        self.candidate_count = candidate_count

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        base = state.best_candidate or state.current_candidate
        if base is None:
            return [self.sample_random(rng, state.iteration + 1, "random")]
        n_random = int(round(self.candidate_count * self.exploration_ratio))
        n_local = self.candidate_count - n_random
        out = [self.sample_random(rng, state.iteration + 1, "fixed-explore") for _ in range(n_random)]
        out += [self.sample_local(base, rng, state.iteration + 1, self.step, "fixed-local")
                for _ in range(max(0, n_local))]
        return out
