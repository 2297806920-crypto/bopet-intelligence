# -*- coding: utf-8 -*-
"""Re-evaluate historical candidates after constraint/evaluator version changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.schemas import CandidatePlan, EvaluationResult


@dataclass
class ReevaluationReport:
    old_version: str
    new_version: str
    active: list[dict] = field(default_factory=list)
    invalidated: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    best_candidate_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "old_version": self.old_version,
            "new_version": self.new_version,
            "active": self.active,
            "invalidated": self.invalidated,
            "history": self.history,
            "best_candidate_id": self.best_candidate_id,
        }


class ReevaluationService:
    def __init__(self, *, maximize: bool = True):
        self.maximize = maximize

    def reevaluate(self, candidates: list[CandidatePlan],
                   evaluator: Callable[[CandidatePlan], EvaluationResult],
                   *, old_version: str, new_version: str) -> ReevaluationReport:
        report = ReevaluationReport(old_version=old_version, new_version=new_version)
        active: list[tuple[float, str]] = []
        for candidate in candidates:
            evaluation = evaluator(candidate)
            if evaluation.evaluation_version != new_version:
                raise ValueError(
                    f"evaluator returned {evaluation.evaluation_version}, expected {new_version}"
                )
            row = {
                "candidate_id": candidate.candidate_id,
                "objective": evaluation.objective_value,
                "hard_feasible": evaluation.hard_feasible,
                "evaluation_version": evaluation.evaluation_version,
            }
            report.history.append(row)
            if evaluation.hard_feasible and evaluation.objective_value is not None:
                report.active.append(row)
                active.append((float(evaluation.objective_value), candidate.candidate_id))
            else:
                row["reason"] = "infeasible under new constraint/evaluation version"
                report.invalidated.append(row)
        if active:
            report.best_candidate_id = (max(active) if self.maximize else min(active))[1]
        return report
