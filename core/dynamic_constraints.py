# -*- coding: utf-8 -*-
"""V3.1 dynamic constraint helpers: applicability, dependency graph, conflict checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.constraints import ConstraintEngine
from core.schemas import CandidatePlan, ConstraintResult, ConstraintStatus, ConstraintType, DecisionVariable


@dataclass(frozen=True)
class ConditionContext:
    polymer: str = "PET"
    equipment: str = "BOPET-line"
    process_stage: str = "stretching"
    thickness_um: float | None = None
    temperature_c: float | None = None


class DependencyCycleError(ValueError):
    pass


class DependencyGraph:
    def __init__(self, variables: list[DecisionVariable]):
        self.variables = {v.variable_id: v for v in variables}
        self.edges = {v.variable_id: list(v.dependency_variables) for v in variables}

    def topological_order(self) -> list[str]:
        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []

        def visit(node: str):
            if node in visiting:
                raise DependencyCycleError(f"cycle detected at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dep in self.edges.get(node, []):
                if dep not in self.edges:
                    raise DependencyCycleError(f"unknown dependency {dep} for {node}")
                visit(dep)
            visiting.remove(node)
            visited.add(node)
            order.append(node)

        for node in self.edges:
            visit(node)
        return order

    def cycles(self) -> bool:
        try:
            self.topological_order()
            return False
        except DependencyCycleError:
            return True


class DynamicConstraintEngine:
    """Filter constraints by material/equipment/stage applicability.

    A non-applicable constraint is NOT_APPLICABLE, never PASS. No safety bound
    is relaxed by an Agent; applicability only selects which evidence applies.
    """

    def __init__(self, variables: list[DecisionVariable], context: ConditionContext,
                 *, require_calibration: bool = False, version: str = "v3.1"):
        self.variables = variables
        self.context = context
        self.require_calibration = require_calibration
        self.version = version
        self.dependency_graph = DependencyGraph(variables)

    def _applicable(self, v: DecisionVariable) -> bool:
        checks = {
            "polymer": self.context.polymer,
            "equipment": self.context.equipment,
            "process_stage": self.context.process_stage,
        }
        for key, actual in checks.items():
            expected = v.material_conditions.get(key) or v.equipment_conditions.get(key)
            if expected is not None and str(expected) != str(actual):
                return False
        for key, actual in (("thickness_um", self.context.thickness_um),
                            ("temperature_c", self.context.temperature_c)):
            expected = v.material_conditions.get(key) or v.equipment_conditions.get(key)
            if expected is not None and actual is not None:
                if isinstance(expected, dict):
                    lo, hi = expected.get("min"), expected.get("max")
                    if (lo is not None and actual < lo) or (hi is not None and actual > hi):
                        return False
                elif abs(float(expected) - float(actual)) > 1e-9:
                    return False
        return True

    def evaluate(self, candidate: CandidatePlan) -> dict[str, Any]:
        active = [v for v in self.variables if self._applicable(v)]
        skipped = [v for v in self.variables if not self._applicable(v)]
        report = ConstraintEngine(active, require_calibration=self.require_calibration,
                                  version=self.version).evaluate(candidate)
        for v in skipped:
            report["results"].append(ConstraintResult(
                constraint_id=f"{v.variable_id}_NOT_APPLICABLE",
                constraint_type=ConstraintType(v.constraint_type),
                status=ConstraintStatus.NOT_APPLICABLE,
                calibration_status=v.calibration_status,
                evidence_ids=v.evidence_ids,
                explanation=f"context {self.context} does not match variable conditions",
            ).model_dump(mode="json"))
        report["not_applicable"] = [v.variable_id for v in skipped]
        report["applicable_count"] = len(active)
        report["context"] = self.context.__dict__
        return report

    def conflicts(self) -> list[str]:
        return ConstraintEngine(self.variables).interval_conflicts()

    def sample_feasibility(self, sampler: Callable[[int], CandidatePlan], n: int = 100) -> dict[str, Any]:
        feasible = 0
        failures: dict[str, int] = {}
        for i in range(n):
            report = self.evaluate(sampler(i))
            if report["hard_feasible"]:
                feasible += 1
            for cid in report.get("hard_failures", []):
                failures[cid] = failures.get(cid, 0) + 1
        return {"n": n, "feasible": feasible, "feasible_ratio": feasible / n if n else 0.0,
                "failure_counts": failures}
