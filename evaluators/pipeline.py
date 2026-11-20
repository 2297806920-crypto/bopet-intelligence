# -*- coding: utf-8 -*-
"""Four-evaluator pipeline used by the V3.1 measure scenario."""

from __future__ import annotations

from typing import Any

from core.schemas import CandidatePlan, DataMode, EvaluationResult
from evaluators.economic import EconomicEvaluator
from evaluators.physical_measures import MeasurePhysicalEvaluator
from evaluators.production import ProductionEvaluator
from evaluators.uncertainty import UncertaintyEvaluator
from scenarios.bopet import UNCALIBRATED_IDS


class EvaluationPipeline:
    def __init__(self, physical=None, production=None, economic=None, uncertainty=None,
                 *, evaluation_version: str = "v3.1", objective_version: str = "v3.1"):
        self.physical = physical or MeasurePhysicalEvaluator()
        self.production = production or ProductionEvaluator()
        self.economic = economic or EconomicEvaluator()
        self.uncertainty = uncertainty or UncertaintyEvaluator()
        self.evaluation_version = evaluation_version
        self.objective_version = objective_version

    def evaluate(self, candidate: CandidatePlan, *,
                 data_mode: DataMode = DataMode.SCENARIO_ESTIMATION) -> EvaluationResult:
        physical = self.physical.evaluate(candidate)
        production = self.production.evaluate(candidate)
        economic = self.economic.evaluate(production)
        missing = list(physical.get("missing_fields", [])) + list(production.get("missing_fields", []))
        uncertainty = self.uncertainty.evaluate(
            missing_fields=missing,
            uncalibrated_count=len(UNCALIBRATED_IDS),
            variable_count=24,
            evidence_grades=["B"],
            scenario_values={
                "conservative": economic.get("annual_net_benefit", 0.0) * 0.7,
                "base": economic.get("annual_net_benefit", 0.0),
                "optimistic": economic.get("annual_net_benefit", 0.0) * 1.3,
            },
        )
        hard = bool(physical.get("hard_feasible")) and bool(production.get("hard_feasible"))
        vector = {
            "qualified_t": float(production["metrics"].get("qualified_t", 0.0)),
            "quality_yield": float(production["metrics"].get("quality_yield", 0.0)),
            "unit_cost": float(production["metrics"].get("unit_cost", 0.0)),
            "annual_net_benefit": float(economic.get("annual_net_benefit", 0.0)),
            "uncertainty": float(uncertainty.get("uncertainty", 0.0)),
        }
        return EvaluationResult(
            physical_result=physical,
            production_result=production,
            economic_result=economic,
            uncertainty_result=uncertainty,
            hard_feasible=hard,
            soft_penalty=0.0,
            objective_value=float(production["metrics"]["objective"]) if hard else None,
            objective_vector=vector,
            objective_version=self.objective_version,
            evaluation_version=self.evaluation_version,
            warnings=(["engineering estimate; not real production"] if hard else []),
            missing_fields=missing,
            data_mode=data_mode,
        )
