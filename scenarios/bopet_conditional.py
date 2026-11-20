# -*- coding: utf-8 -*-
"""BOPET 24-variable scenario with demonstrative conditional tags.

The condition tags below are scenario applicability labels, not plant safety
interlocks. They show how the dynamic constraint engine filters evidence; they
must be replaced by field-verified conditions before any real use.
"""

from __future__ import annotations

from typing import Any

from core.dynamic_constraints import ConditionContext, DynamicConstraintEngine
from core.schemas import CandidatePlan, EvaluationResult
from scenarios.bopet import BOPET_BASELINE, BOPET_VARIABLES
from scenarios.bopet_process import BOPETProcessScenario


def conditioned_variables():
    out = []
    for v in BOPET_VARIABLES:
        update: dict[str, Any] = {}
        if v.variable_id in ("V11", "V12"):
            update["material_conditions"] = {"polymer": "PET", "process_stage": "stretching"}
        elif v.variable_id in ("V17", "V18", "V19"):
            update["material_conditions"] = {"polymer": "PET"}
        elif v.variable_id in ("V15", "V16"):
            update["equipment_conditions"] = {"equipment": "BOPET-line", "process_stage": "winding"}
        elif v.variable_id in ("V20", "V21", "V22", "V23"):
            update["material_conditions"] = {"polymer": "PET", "process_stage": "casting"}
        out.append(v.model_copy(update=update) if update else v)
    return out


class BOPETConditionalScenario(BOPETProcessScenario):
    name = "bopet_conditional"
    evaluation_version = "v3.1"

    def __init__(self, context: ConditionContext | None = None):
        self.context = context or ConditionContext()
        self.variables = conditioned_variables()

    def evaluate(self, candidate: CandidatePlan) -> EvaluationResult:
        result = super().evaluate(candidate)
        params = dict(BOPET_BASELINE)
        params.update(candidate.parameters)
        filled = CandidatePlan(candidate_id=candidate.candidate_id, iteration=candidate.iteration,
                               parameters=params, generation_strategy=candidate.generation_strategy,
                               data_mode=self.data_mode)
        dynamic = DynamicConstraintEngine(self.variables, self.context).evaluate(filled)
        hard = bool(result.hard_feasible) and bool(dynamic["hard_feasible"])
        result.physical_result["dynamic_constraint_report"] = dynamic
        result.hard_feasible = hard
        if not hard:
            result.objective_value = None
            result.warnings.append("dynamic constraint context made candidate infeasible")
        return result
