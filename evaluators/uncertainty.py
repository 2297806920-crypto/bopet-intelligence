# -*- coding: utf-8 -*-
"""Explainable uncertainty information, not a statistical confidence interval."""

from __future__ import annotations

from typing import Any


class UncertaintyEvaluator:
    def evaluate(self, *, missing_fields: list[str] | None = None,
                 uncalibrated_count: int = 0, variable_count: int = 24,
                 evidence_grades: list[str] | None = None,
                 scenario_values: dict[str, float] | None = None) -> dict[str, Any]:
        missing = list(missing_fields or [])
        missing_ratio = len(missing) / max(1, len(missing) + variable_count)
        uncal_ratio = uncalibrated_count / max(1, variable_count)
        grades = evidence_grades or []
        grade_penalty = sum({"A": 0.0, "B": 0.1, "C": 0.2}.get(g, 0.25) for g in grades) / max(1, len(grades))
        spread = 0.0
        if scenario_values and len(scenario_values) >= 2:
            vals = list(scenario_values.values())
            spread = (max(vals) - min(vals)) / max(abs(sum(vals) / len(vals)), 1e-9)
        score = min(1.0, 0.4 * missing_ratio + 0.35 * uncal_ratio + 0.15 * grade_penalty + 0.10 * min(spread, 1.0))
        return {
            "uncertainty": score,
            "missing_ratio": missing_ratio,
            "uncalibrated_ratio": uncal_ratio,
            "evidence_grade_penalty": grade_penalty,
            "scenario_spread": spread,
            "missing_fields": missing,
            "types": {
                "statistical": "not estimated: no distribution/replicates",
                "scenario_range": "provided scenario spread only",
                "knowledge_gap": "uncalibrated variables and missing fields",
                "configured_risk": "not used as a probability",
            },
            "ci95": None,
            "note": "Not a statistically valid 95% confidence interval.",
        }
