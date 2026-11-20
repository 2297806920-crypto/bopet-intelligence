# -*- coding: utf-8 -*-
"""Adapter: optimize the existing BOPET measure model (M1-M7 levels)."""

from __future__ import annotations

from typing import Any

from core.schemas import CandidatePlan, DataMode, EvaluationResult
from evaluators.pipeline import EvaluationPipeline
from production_model import MEASURES

MEASURE_IDS = [m["id"] for m in MEASURES]


class BOPETMeasureScenario:
    name = "bopet_measures"
    data_mode = DataMode.SCENARIO_ESTIMATION
    variable_bounds = {m: (0.0, 1.0) for m in MEASURE_IDS}
    discrete = True
    evaluation_version = "v3.1"
    description = "Existing production_model measure plan; engineering estimate, not plant data"

    def __init__(self):
        self.pipeline = EvaluationPipeline(evaluation_version="v3.1", objective_version="v3.1")

    def sample(self, rng, iteration: int, strategy: str = "random") -> CandidatePlan:
        params = {m: float(rng.integers(0, 2)) for m in MEASURE_IDS}
        return CandidatePlan(
            candidate_id=f"bopet-{iteration}-{rng.randrange(10**6):06d}",
            iteration=iteration,
            parameters=params,
            generation_strategy=strategy,
            data_mode=self.data_mode,
        )

    def initial_candidate(self) -> CandidatePlan:
        return CandidatePlan(
            candidate_id="bopet-baseline",
            iteration=0,
            parameters={m: 0.0 for m in MEASURE_IDS},
            generation_strategy="baseline",
            data_mode=self.data_mode,
        )

    def evaluate(self, candidate: CandidatePlan) -> EvaluationResult:
        return self.pipeline.evaluate(candidate, data_mode=self.data_mode)
