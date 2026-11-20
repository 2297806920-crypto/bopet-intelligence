# -*- coding: utf-8 -*-
"""Search primitives shared by the adaptive engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.schemas import AgentDecision, CandidatePlan, OptimizationState


@dataclass
class SearchConfig:
    search_step: float = 0.15
    exploration_ratio: float = 0.30
    candidate_count: int = 1
    target_variables: list[str] | None = None
    optimizer_type: str = "adaptive"


class BaseSearch:
    name = "base"

    def __init__(self, scenario: Any, *, seed: int = 7):
        self.scenario = scenario
        self.bounds = dict(getattr(scenario, "variable_bounds"))
        self.discrete = bool(getattr(scenario, "discrete", False))

    def sample_random(self, rng, iteration: int, strategy: str):
        params = {}
        for key, (lo, hi) in self.bounds.items():
            value = float(rng.uniform(lo, hi))
            params[key] = float(round(value)) if self.discrete else value
        return CandidatePlan(
            candidate_id=f"{self.name}-{iteration}-{rng.randrange(10**6):06d}",
            iteration=iteration,
            parameters=params,
            generation_strategy=strategy,
            data_mode=getattr(self.scenario, "data_mode"),
        )

    def sample_local(self, base: CandidatePlan, rng, iteration: int, step: float,
                     strategy: str, variables: list[str] | None = None):
        params = dict(base.parameters)
        keys = variables or list(self.bounds)
        if self.discrete:
            keys = [rng.choice(keys)] if keys else []
        for key in keys:
            if key not in self.bounds:
                continue
            lo, hi = self.bounds[key]
            value = float(params.get(key, (lo + hi) / 2.0))
            if self.discrete:
                value = 1.0 if value < 0.5 else 0.0
            else:
                value += float(rng.normalvariate(0.0, max(step, 1e-6) * (hi - lo)))
                value = min(hi, max(lo, value))
            params[key] = value
        return CandidatePlan(
            candidate_id=f"{self.name}-{iteration}-{rng.randrange(10**6):06d}",
            iteration=iteration,
            parameters=params,
            generation_strategy=strategy,
            parent_candidate_id=base.candidate_id,
            data_mode=getattr(self.scenario, "data_mode"),
        )

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        raise NotImplementedError

