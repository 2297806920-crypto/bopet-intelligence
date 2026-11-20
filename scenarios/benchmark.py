# -*- coding: utf-8 -*-
"""Small, honest benchmark scenario for optimizer comparisons."""

from __future__ import annotations

import math
from typing import Any

from core.schemas import CandidatePlan, DataMode, EvaluationResult


class BenchmarkScenario:
    name = "benchmark_2d"
    data_mode = DataMode.SIMULATION_ONLY
    variable_bounds = {"x1": (0.0, 1.0), "x2": (0.0, 1.0)}
    optimum = {"x1": 0.35, "x2": 0.72}

    def sample(self, rng, iteration: int, strategy: str = "random") -> CandidatePlan:
        params = {k: rng.uniform(lo, hi) for k, (lo, hi) in self.variable_bounds.items()}
        return CandidatePlan(
            candidate_id=f"bench-{iteration}-{rng.randrange(10**6):06d}",
            iteration=iteration,
            parameters=params,
            generation_strategy=strategy,
            data_mode=self.data_mode,
        )

    def initial_candidate(self) -> CandidatePlan:
        return CandidatePlan(
            candidate_id="bench-baseline",
            iteration=0,
            parameters={k: (lo + hi) / 2.0 for k, (lo, hi) in self.variable_bounds.items()},
            generation_strategy="baseline",
            data_mode=self.data_mode,
        )

    def evaluate(self, candidate: CandidatePlan) -> EvaluationResult:
        x1 = float(candidate.parameters.get("x1", 0.0))
        x2 = float(candidate.parameters.get("x2", 0.0))
        # Higher is better; unique optimum 1.0 at (0.35, 0.72).
        objective = 1.0 - ((x1 - 0.35) ** 2 + (x2 - 0.72) ** 2) / 0.5
        feasible = 0.0 <= x1 <= 1.0 and 0.0 <= x2 <= 1.0
        return EvaluationResult(
            physical_result={"hard_feasible": feasible, "missing_fields": []},
            production_result={"objective": objective, "metrics": {"x1": x1, "x2": x2}},
            economic_result={},
            uncertainty_result={"uncertainty": 0.0, "missing_ratio": 0.0},
            hard_feasible=feasible,
            objective_value=objective if feasible else None,
            data_mode=self.data_mode,
        )

    def random_candidate(self, rng, iteration: int) -> CandidatePlan:
        return self.sample(rng, iteration, "random")
