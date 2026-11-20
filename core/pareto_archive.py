# -*- coding: utf-8 -*-
"""Non-dominated Pareto archive for V3.1 multi-objective candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.schemas import CandidatePlan, EvaluationResult


class ParetoArchive:
    def __init__(self, directions: dict[str, str], *, evaluation_version: str = "v3.1",
                 max_size: int = 50, maximize_scalar: bool = True):
        self.directions = directions
        self.evaluation_version = evaluation_version
        self.max_size = max_size
        self.maximize_scalar = maximize_scalar
        self.front: list[tuple[CandidatePlan, EvaluationResult]] = []
        self.best: CandidatePlan | None = None
        self.best_evaluation: EvaluationResult | None = None
        self.history: list[dict[str, Any]] = []

    def _dominates(self, a: dict[str, float], b: dict[str, float]) -> bool:
        better_or_equal = True
        strictly = False
        for key, direction in self.directions.items():
            av, bv = float(a[key]), float(b[key])
            if direction == "max":
                if av < bv:
                    better_or_equal = False
                    break
                if av > bv:
                    strictly = True
            else:
                if av > bv:
                    better_or_equal = False
                    break
                if av < bv:
                    strictly = True
        return better_or_equal and strictly

    def consider(self, candidate: CandidatePlan, evaluation: EvaluationResult) -> bool:
        if not evaluation.hard_feasible or not evaluation.objective_vector:
            return False
        if evaluation.evaluation_version != self.evaluation_version:
            return False
        if any(k not in evaluation.objective_vector for k in self.directions):
            return False
        vector = {k: float(evaluation.objective_vector[k]) for k in self.directions}
        for _, existing in self.front:
            if self._dominates(existing.objective_vector, vector):
                self.history.append({"candidate_id": candidate.candidate_id, "accepted": False,
                                     "reason": "dominated"})
                return False
        self.front = [(c, e) for c, e in self.front
                      if not self._dominates(vector, e.objective_vector)]
        self.front.append((candidate, evaluation))
        self.front = self.front[-self.max_size:]
        if evaluation.objective_value is not None:
            if self.best_evaluation is None:
                self.best, self.best_evaluation = candidate, evaluation
            else:
                old = float(self.best_evaluation.objective_value or 0.0)
                new = float(evaluation.objective_value)
                better = new > old if self.maximize_scalar else new < old
                if better:
                    self.best, self.best_evaluation = candidate, evaluation
        self.history.append({"candidate_id": candidate.candidate_id, "accepted": True})
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "directions": self.directions,
            "evaluation_version": self.evaluation_version,
            "front": [{"candidate": c.model_dump(mode="json"), "evaluation": e.model_dump(mode="json")}
                      for c, e in self.front],
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
