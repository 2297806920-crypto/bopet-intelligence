# -*- coding: utf-8 -*-
"""Synthetic math scenarios for V3.1 algorithm experiments.

All scenarios are explicitly SIMULATION_ONLY. They test algorithm behavior, not
BOPET production or plant safety.
"""

from __future__ import annotations

import math
from typing import Callable

from core.schemas import CandidatePlan, DataMode, EvaluationResult


class MathScenario:
    name = "math"
    data_mode = DataMode.SIMULATION_ONLY
    evaluation_version = "v3.1"
    variable_bounds: dict[str, tuple[float, float]] = {}
    optimum: dict[str, float] = {}

    def sample(self, rng, iteration: int, strategy: str = "random") -> CandidatePlan:
        params = {k: rng.uniform(lo, hi) for k, (lo, hi) in self.variable_bounds.items()}
        return CandidatePlan(candidate_id=f"{self.name}-{iteration}-{rng.randrange(10**6):06d}",
                             iteration=iteration, parameters=params,
                             generation_strategy=strategy, data_mode=self.data_mode)

    def initial_candidate(self) -> CandidatePlan:
        return CandidatePlan(candidate_id=f"{self.name}-baseline", iteration=0,
                             parameters={k: (lo + hi) / 2 for k, (lo, hi) in self.variable_bounds.items()},
                             generation_strategy="baseline", data_mode=self.data_mode)

    def _result(self, candidate: CandidatePlan, objective: float, feasible: bool,
                *, vector: dict[str, float] | None = None,
                note: str = "") -> EvaluationResult:
        return EvaluationResult(
            physical_result={"hard_feasible": feasible, "missing_fields": []},
            production_result={"objective": objective, "vector": vector or {}, "note": note},
            uncertainty_result={"uncertainty": 0.0},
            hard_feasible=feasible,
            objective_value=objective if feasible else None,
            objective_vector=vector or {},
            evaluation_version=self.evaluation_version,
            data_mode=self.data_mode,
        )

    def evaluate(self, candidate: CandidatePlan) -> EvaluationResult:
        raise NotImplementedError


class Sphere5D(MathScenario):
    name = "sphere5d"
    variable_bounds = {f"x{i}": (0.0, 1.0) for i in range(1, 6)}
    optimum = {k: 0.5 for k in variable_bounds}

    def initial_candidate(self):
        return CandidatePlan(candidate_id="sphere5d-baseline", iteration=0,
                             parameters={k: 0.2 for k in self.variable_bounds},
                             generation_strategy="baseline", data_mode=self.data_mode)

    def evaluate(self, candidate):
        d2 = sum((float(candidate.parameters.get(k, 0.5)) - 0.5) ** 2 for k in self.variable_bounds)
        objective = 1.0 / (1.0 + d2)
        return self._result(candidate, objective, True, note="single-peak/high-dim")


class Rastrigin5D(MathScenario):
    name = "rastrigin5d"
    variable_bounds = {f"x{i}": (0.0, 1.0) for i in range(1, 6)}
    optimum = {k: 0.5 for k in variable_bounds}

    def initial_candidate(self):
        return CandidatePlan(candidate_id="rastrigin5d-baseline", iteration=0,
                             parameters={k: 0.2 for k in self.variable_bounds},
                             generation_strategy="baseline", data_mode=self.data_mode)

    def evaluate(self, candidate):
        z = [float(candidate.parameters.get(k, 0.5)) - 0.5 for k in self.variable_bounds]
        val = 10 * len(z) + sum(v * v - 10 * math.cos(2 * math.pi * v) for v in z)
        objective = 1.0 / (1.0 + val)
        return self._result(candidate, objective, True, note="multimodal")


class NarrowFeasible2D(MathScenario):
    name = "narrow2d"
    variable_bounds = {"x1": (0.0, 1.0), "x2": (0.0, 1.0)}
    optimum = {"x1": 0.25, "x2": 0.25}

    def initial_candidate(self):
        return CandidatePlan(candidate_id="narrow2d-baseline", iteration=0,
                             parameters={"x1": 0.3, "x2": 0.3},
                             generation_strategy="baseline", data_mode=self.data_mode)

    def evaluate(self, candidate):
        x1 = float(candidate.parameters.get("x1", 0.5)); x2 = float(candidate.parameters.get("x2", 0.5))
        feasible = x1 + x2 <= 0.8
        d2 = (x1 - 0.25) ** 2 + (x2 - 0.25) ** 2
        objective = 1.0 / (1.0 + d2)
        return self._result(candidate, objective, feasible, note="narrow linear feasible region")


class DynamicConstraint2D(MathScenario):
    name = "dynamic2d"
    variable_bounds = {"x1": (0.0, 1.0), "x2": (0.0, 1.0)}
    optimum = {"x1": 0.2, "x2": 0.8}

    def evaluate(self, candidate):
        x1 = float(candidate.parameters.get("x1", 0.5)); x2 = float(candidate.parameters.get("x2", 0.5))
        limit = 0.7 if int(candidate.iteration) < 8 else 0.4
        feasible = x1 <= limit
        objective = 1.0 / (1.0 + (x1 - 0.2) ** 2 + (x2 - 0.8) ** 2)
        return self._result(candidate, objective, feasible, note=f"dynamic x1<={limit}")


class MultiObjective2D(MathScenario):
    name = "multiobj2d"
    variable_bounds = {"x1": (0.0, 1.0), "x2": (0.0, 1.0)}
    optimum = {"x1": 0.3, "x2": 0.3}

    def evaluate(self, candidate):
        x1 = float(candidate.parameters.get("x1", 0.5)); x2 = float(candidate.parameters.get("x2", 0.5))
        quality = 1.0 / (1.0 + (x1 - 0.2) ** 2 + (x2 - 0.2) ** 2)
        cost = (x1 - 0.8) ** 2 + (x2 - 0.8) ** 2
        scalar = 0.7 * quality - 0.3 * cost
        vector = {"quality": quality, "cost": cost}
        return self._result(candidate, scalar, True, vector=vector, note="multi-objective weight 0.7/-0.3")


SCENARIOS: dict[str, Callable[[], MathScenario]] = {
    "sphere5d": Sphere5D,
    "rastrigin5d": Rastrigin5D,
    "narrow2d": NarrowFeasible2D,
    "dynamic2d": DynamicConstraint2D,
    "multiobj2d": MultiObjective2D,
}
