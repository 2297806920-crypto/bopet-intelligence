# -*- coding: utf-8 -*-
"""Anti-regression archive with evaluation-version guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.schemas import CandidatePlan, EvaluationResult


class ArchiveError(RuntimeError):
    pass


class AntiRegressionArchive:
    def __init__(self, *, maximize: bool = True, evaluation_version: str = "v3.0",
                 objective_name: str = "objective_value"):
        self.maximize = maximize
        self.evaluation_version = evaluation_version
        self.objective_name = objective_name
        self.best: CandidatePlan | None = None
        self.best_evaluation: EvaluationResult | None = None
        self.history: list[dict[str, Any]] = []

    def consider(self, candidate: CandidatePlan, evaluation: EvaluationResult) -> bool:
        """Update only if feasible, comparable, and strictly better."""
        if not evaluation.hard_feasible:
            return False
        if evaluation.objective_value is None:
            return False
        if evaluation.evaluation_version != self.evaluation_version:
            self.history.append({
                "candidate_id": candidate.candidate_id,
                "accepted": False,
                "reason": "evaluation version mismatch",
            })
            return False
        if self.best is None or self.best_evaluation is None:
            self.best = candidate
            self.best_evaluation = evaluation
            self.history.append({"candidate_id": candidate.candidate_id, "accepted": True})
            return True

        old = float(self.best_evaluation.objective_value)
        new = float(evaluation.objective_value)
        better = new > old if self.maximize else new < old
        if better:
            self.best = candidate
            self.best_evaluation = evaluation
            self.history.append({"candidate_id": candidate.candidate_id, "accepted": True})
            return True
        self.history.append({"candidate_id": candidate.candidate_id, "accepted": False})
        return False

    def rollback(self) -> CandidatePlan | None:
        return self.best

    def to_dict(self) -> dict[str, Any]:
        return {
            "maximize": self.maximize,
            "evaluation_version": self.evaluation_version,
            "best_candidate": self.best.model_dump(mode="json") if self.best else None,
            "best_evaluation": self.best_evaluation.model_dump(mode="json") if self.best_evaluation else None,
            "history": self.history,
        }

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: str | Path) -> "AntiRegressionArchive":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AntiRegressionArchive":
        obj = cls(maximize=bool(data.get("maximize", True)),
                  evaluation_version=str(data.get("evaluation_version", "v3.0")))
        if data.get("best_candidate"):
            obj.best = CandidatePlan.model_validate(data["best_candidate"])
        if data.get("best_evaluation"):
            obj.best_evaluation = EvaluationResult.model_validate(data["best_evaluation"])
        obj.history = data.get("history", [])
        return obj
