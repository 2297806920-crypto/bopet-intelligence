# -*- coding: utf-8 -*-
"""Physical evaluator: hard constraints + F05 mass balance."""

from __future__ import annotations

from typing import Any

from core.constraints import ConstraintEngine
from core.physics import mass_balance_residual
from core.schemas import CandidatePlan


class PhysicalEvaluator:
    def __init__(self, engine: ConstraintEngine, *, mass_tolerance: float = 1e-3):
        self.engine = engine
        self.mass_tolerance = float(mass_tolerance)

    def evaluate(self, candidate: CandidatePlan,
                 mass_in_kg_s: float | None = None,
                 mass_out_kg_s: float | None = None) -> dict[str, Any]:
        report = self.engine.evaluate(candidate)
        missing = list(report.get("unknown_constraints", []))
        residual = None
        residual_ok = None
        if mass_in_kg_s is not None and mass_out_kg_s is not None:
            residual = mass_balance_residual(mass_in_kg_s, mass_out_kg_s)
            residual_ok = residual <= self.mass_tolerance
        else:
            missing.append("mass_flow_in/out")
        hard = bool(report["hard_feasible"]) and (residual_ok is not False)
        return {
            "hard_feasible": hard,
            "constraint_report": report,
            "mass_balance_residual": residual,
            "mass_balance_ok": residual_ok,
            "mass_tolerance": self.mass_tolerance,
            "missing_fields": missing,
            "violated_constraints": report.get("hard_failures", []),
            "evidence_applicability": "offline pre-check; calibration required before approval",
        }
