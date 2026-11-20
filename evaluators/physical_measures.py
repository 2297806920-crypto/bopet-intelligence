# -*- coding: utf-8 -*-
"""Physical/constraint evaluator for the M1-M7 measure layer."""

from __future__ import annotations

from typing import Any

from core.schemas import CandidatePlan
from production_model import ASSUMPTIONS, BASELINE, plan_cost


class MeasurePhysicalEvaluator:
    def evaluate(self, candidate: CandidatePlan) -> dict[str, Any]:
        plan = {"measures": {m: 1.0 for m, level in candidate.parameters.items() if float(level) > 0.5}}
        cost = plan_cost(plan)
        budget_ok = cost["capex_wan"] <= BASELINE["budget_wan"]
        install_ok = cost["install_h"] <= ASSUMPTIONS["max_total_install_h"]
        single_ok = cost["max_single_h"] <= BASELINE["shutdown_window_h"]
        hard = budget_ok and install_ok and single_ok
        failures = []
        if not budget_ok:
            failures.append("budget")
        if not install_ok:
            failures.append("install")
        if not single_ok:
            failures.append("single_shutdown")
        return {
            "hard_feasible": hard,
            "constraint_report": {
                "budget_ok": budget_ok,
                "install_ok": install_ok,
                "single_ok": single_ok,
                "hard_failures": failures,
            },
            "capex_wan": cost["capex_wan"],
            "install_h": cost["install_h"],
            "max_single_h": cost["max_single_h"],
            "missing_fields": [],
            "note": "measure-layer physical/constraint precheck; not a 24-variable mass balance",
        }
