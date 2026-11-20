# -*- coding: utf-8 -*-
"""Multi-level constraint engine (bounds, soft windows, calibration, conditional)."""

from __future__ import annotations

import math
from typing import Any

from core.schemas import (
    CandidatePlan,
    ConstraintResult,
    ConstraintStatus,
    ConstraintType,
    DecisionVariable,
)


class ConstraintEngine:
    """Evaluate a candidate against configured variable windows.

    Important semantics:
    - a performance window is never a physical hard constraint;
    - UNKNOWN is never treated as PASS;
    - uncalibrated literature bounds can be evaluated offline, but when
      ``require_calibration=True`` they become UNKNOWN and block approval.
    """

    def __init__(self, variables: list[DecisionVariable], *, require_calibration: bool = False,
                 soft_weight: float = 1.0, quadratic: bool = False,
                 version: str = "v3.0"):
        self.variables = {v.variable_id: v for v in variables}
        self.require_calibration = require_calibration
        self.soft_weight = soft_weight
        self.quadratic = quadratic
        self.version = version

    def evaluate(self, candidate: CandidatePlan) -> dict[str, Any]:
        results: list[ConstraintResult] = []
        for vid, var in self.variables.items():
            ctype = ConstraintType(var.constraint_type)
            if var.adjustable is False:
                results.append(ConstraintResult(
                    constraint_id=f"{vid}_DERIVED",
                    constraint_type=ConstraintType.DERIVED,
                    status=ConstraintStatus.NOT_APPLICABLE,
                    actual_value=candidate.derived_parameters.get(vid),
                    expected_range=(var.lower_bound, var.upper_bound),
                    evidence_ids=var.evidence_ids,
                    calibration_status=var.calibration_status,
                    explanation="derived variable; not an independent search variable",
                ))
                continue
            if vid not in candidate.parameters:
                results.append(ConstraintResult(
                    constraint_id=f"{vid}_MISSING",
                    constraint_type=ConstraintType.HARD if ctype in (
                        ConstraintType.HARD, ConstraintType.COUPLING) else ctype,
                    status=ConstraintStatus.UNKNOWN,
                    expected_range=(var.lower_bound, var.upper_bound),
                    evidence_ids=var.evidence_ids,
                    calibration_status=var.calibration_status,
                    explanation="required decision variable is missing",
                ))
                continue

            x = float(candidate.parameters[vid])
            hard = ctype in (ConstraintType.HARD, ConstraintType.COUPLING)
            status = ConstraintStatus.PASS
            violation = 0.0
            penalty = 0.0
            explanation = ""

            if not math.isfinite(x):
                status = ConstraintStatus.FAIL if hard else ConstraintStatus.UNKNOWN
                violation = math.inf
                explanation = "non-finite value"
            elif x < var.lower_bound or x > var.upper_bound:
                violation = (var.lower_bound - x) if x < var.lower_bound else (x - var.upper_bound)
                if hard:
                    status = ConstraintStatus.FAIL
                    explanation = f"outside hard bound [{var.lower_bound}, {var.upper_bound}]"
                else:
                    status = ConstraintStatus.PASS
                    explanation = "outside preferred window; soft penalty only"
            elif self.require_calibration and hard and var.calibration_status != "CALIBRATED":
                status = ConstraintStatus.UNKNOWN
                explanation = "hard bound is not field-calibrated; approval blocked"

            if ctype in (ConstraintType.SOFT, ConstraintType.PERFORMANCE):
                penalty = self._soft_penalty(var, x)
                if penalty > 0 and not explanation:
                    explanation = "outside preferred window; not physical infeasibility"

            results.append(ConstraintResult(
                constraint_id=f"{vid}_{ctype.value}",
                constraint_type=ctype,
                status=status,
                actual_value=x,
                expected_range=(var.lower_bound, var.upper_bound),
                violation=violation,
                penalty=penalty,
                safety_margin=min(x - var.lower_bound, var.upper_bound - x),
                evidence_ids=var.evidence_ids,
                calibration_status=var.calibration_status,
                explanation=explanation,
            ))

        hard = [r for r in results if r.constraint_type in (ConstraintType.HARD, ConstraintType.COUPLING)]
        unknown = [r for r in hard if r.status == ConstraintStatus.UNKNOWN]
        failed = [r for r in hard if r.status == ConstraintStatus.FAIL]
        hard_feasible = not failed and not unknown
        soft_penalty = sum(float(r.penalty) for r in results)
        compliance = (1.0 if hard_feasible else 0.0) * math.exp(-soft_penalty)
        return {
            "results": [r.model_dump(mode="json") for r in results],
            "hard_feasible": hard_feasible,
            "soft_penalty": soft_penalty,
            "compliance": compliance,
            "hard_failures": [r.constraint_id for r in failed],
            "unknown_constraints": [r.constraint_id for r in unknown],
            "constraint_version": self.version,
            "hard_checked": len(hard),
        }

    def _soft_penalty(self, var: DecisionVariable, x: float) -> float:
        if var.preferred_range is None:
            return 0.0
        lo, hi = var.preferred_range
        center = (lo + hi) / 2.0
        half = max((hi - lo) / 2.0, 1e-9)
        scale = max(var.upper_bound - var.lower_bound, 1e-9)
        d = max(0.0, abs(x - center) - half) / scale
        if self.quadratic:
            d = d * d
        return self.soft_weight * d

    def interval_conflicts(self) -> list[str]:
        """Return variables whose configured intervals are empty."""
        out = []
        for v in self.variables.values():
            if v.lower_bound > v.upper_bound:
                out.append(v.variable_id)
        return out

