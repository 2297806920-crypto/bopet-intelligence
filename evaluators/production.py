# -*- coding: utf-8 -*-
"""Production evaluator for the existing BOPET measure model."""

from __future__ import annotations

from typing import Any

from core.schemas import CandidatePlan, DataMode
from production_model import BASELINE, evaluate_plan


class ProductionEvaluator:
    data_mode = DataMode.SCENARIO_ESTIMATION

    def evaluate(self, candidate: CandidatePlan) -> dict[str, Any]:
        active = {m: 1.0 for m, level in candidate.parameters.items() if float(level) > 0.5}
        result = evaluate_plan({"action": "exploit", "measures": active})
        hard = (
            result["capex_wan"] <= BASELINE["budget_wan"]
            and result["install_h"] <= 192.0
            and result["max_single_h"] <= BASELINE["shutdown_window_h"]
        )
        return {
            "hard_feasible": hard,
            "active_measures": sorted(active),
            "metrics": {
                "qualified_t": result["qualified_t"],
                "quality_yield": result["quality_yield"],
                "demand_fill": result["demand_fill"],
                "downtime_h": result["downtime_h"],
                "transition_h": result["transition_h"],
                "unit_cost": result["unit_cost"],
                "contribution": result["contribution"],
                "capex_wan": result["capex_wan"],
                "install_h": result["install_h"],
                "max_single_h": result["max_single_h"],
                "objective": result["objective"],
            },
            "missing_fields": [],
            "data_mode": self.data_mode.value,
            "revenue_source": "qualified-product revenue - material - energy - capex amortization - inventory",
            "double_counting_check": "capex is amortized once; downtime/transition are not separately added as revenue",
        }
