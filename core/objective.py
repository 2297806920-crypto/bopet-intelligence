# -*- coding: utf-8 -*-
"""Transparent multi-objective vector and Pareto utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ObjectiveTerm:
    name: str
    key: str
    direction: str  # "max" or "min"
    weight: float = 1.0
    lower: float | None = None
    upper: float | None = None


class ObjectiveError(ValueError):
    pass


def normalize(value: float, lower: float, upper: float, direction: str) -> float:
    if upper <= lower:
        raise ObjectiveError("upper must be greater than lower")
    x = (float(value) - lower) / (upper - lower)
    x = min(1.0, max(0.0, x))
    return x if direction == "max" else 1.0 - x


def weighted_objective(metrics: dict[str, float], terms: list[ObjectiveTerm]) -> dict[str, Any]:
    if not terms:
        raise ObjectiveError("at least one objective term is required")
    total_weight = sum(t.weight for t in terms)
    if total_weight <= 0:
        raise ObjectiveError("weights must sum to a positive value")
    values: dict[str, float] = {}
    weighted = 0.0
    missing: list[str] = []
    for term in terms:
        if term.key not in metrics or metrics[term.key] is None:
            missing.append(term.key)
            continue
        if term.lower is None or term.upper is None:
            raise ObjectiveError(f"normalization bounds missing for {term.key}")
        x = normalize(metrics[term.key], term.lower, term.upper, term.direction)
        values[term.key] = x
        weighted += term.weight * x
    if missing:
        # Do not silently treat missing metrics as zero.
        return {"value": None, "normalized": values, "missing": missing,
                "reason": "missing metrics are not defaulted to zero"}
    return {"value": weighted / total_weight, "normalized": values, "missing": []}


def pareto_front(points: Iterable[dict[str, float]], directions: dict[str, str]) -> list[dict[str, float]]:
    """Return non-dominated points; directions map key->max/min."""
    data = list(points)
    front = []
    for p in data:
        dominated = False
        for q in data:
            if q is p:
                continue
            better_or_equal = True
            strictly_better = False
            for key, direction in directions.items():
                a, b = float(p[key]), float(q[key])
                if direction == "max":
                    if b < a:
                        better_or_equal = False
                        break
                    if b > a:
                        strictly_better = True
                else:
                    if b > a:
                        better_or_equal = False
                        break
                    if b < a:
                        strictly_better = True
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(p)
    return front
