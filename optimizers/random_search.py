# -*- coding: utf-8 -*-
"""Baseline A: pure random search."""

from __future__ import annotations

from core.schemas import AgentDecision, CandidatePlan, OptimizationState
from optimizers.base import BaseSearch


class RandomSearch(BaseSearch):
    name = "random"

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        return [self.sample_random(rng, state.iteration + 1, "random")]


class FixedLocalSearch(BaseSearch):
    name = "fixed-local"

    def __init__(self, scenario, *, seed: int = 7, step: float = 0.12):
        super().__init__(scenario, seed=seed)
        self.step = step

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        base = state.best_candidate or state.current_candidate
        if base is None:
            return [self.sample_random(rng, state.iteration + 1, "random")]
        return [self.sample_local(base, rng, state.iteration + 1, self.step, "local")]
