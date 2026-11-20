# -*- coding: utf-8 -*-
"""Deterministic state diagnosis for adaptive search.

V3.1 fixes a V3.0 failure: no-improvement is counted in **iterations**, not in
candidate records. A round with several candidates must not trigger stagnation
after one bad candidate.
"""

from __future__ import annotations

from typing import Any

from core.schemas import OptimizationState, Strategy


class StateAnalyzer:
    def __init__(self, *, stagnation_rounds: int = 3, low_feasibility: float = 0.2,
                 high_uncertainty: float = 0.6):
        self.stagnation_rounds = stagnation_rounds
        self.low_feasibility = low_feasibility
        self.high_uncertainty = high_uncertainty

    def analyze(self, records: list[dict[str, Any]], iteration: int,
                best_objective: float | None = None,
                current_strategy: Strategy = Strategy.EXPLORE) -> OptimizationState:
        objectives = [float(r["objective"]) for r in records if r.get("objective") is not None]
        feasible = [bool(r.get("hard_feasible")) for r in records]
        hard_fail = [not f for f in feasible]
        soft = [float(r.get("soft_penalty") or 0.0) for r in records]
        unc = [float(r.get("uncertainty") or 0.0) for r in records]

        ratio = sum(feasible) / len(feasible) if feasible else 0.0
        hard_freq = sum(hard_fail) / len(hard_fail) if hard_fail else 0.0
        no_improve = self._rounds_without_improvement(records, iteration, best_objective)
        improvement = self._best_so_far_improvement(records)
        recent = objectives[-5:]

        labels: list[str] = []
        if ratio < self.low_feasibility or hard_freq > 0.8:
            labels.append("CONSTRAINT_CONFLICT")
            labels.append("LOW_FEASIBILITY")
        if hard_fail and hard_fail[-1]:
            labels.append("HARD_CONSTRAINT_VIOLATION")
        if no_improve >= self.stagnation_rounds:
            labels.append("STAGNATION")
        if unc and unc[-1] >= self.high_uncertainty:
            labels.append("HIGH_UNCERTAINTY")
        if soft and len(soft) >= 2 and soft[-1] > soft[-2] + 1e-9:
            labels.append("SOFT_CONSTRAINT_DEVIATION")
        if improvement > 1e-4:
            labels.append("IMPROVING")
        if iteration >= 5 and no_improve >= 5:
            labels.append("CONVERGED")
        if not labels:
            labels.append("EXPLORING")

        return OptimizationState(
            iteration=iteration,
            recent_objectives=recent,
            feasible_candidate_ratio=ratio,
            hard_violation_frequency=hard_freq,
            soft_penalty_trend=soft[-10:],
            uncertainty_trend=unc[-10:],
            improvement_rate=improvement,
            no_improvement_rounds=no_improve,
            search_diversity=self._diversity(records),
            current_strategy=current_strategy,
            state_labels=labels,
        )

    @staticmethod
    def _rounds_without_improvement(records: list[dict[str, Any]], iteration: int,
                                    best_objective: float | None) -> int:
        objective_records = [(int(r.get("iteration", 0)), float(r["objective"]))
                             for r in records if r.get("objective") is not None]
        if not objective_records:
            return 0
        best_seen = (max(v for _, v in objective_records) if best_objective is None
                     else float(best_objective))
        best_iters = [it for it, value in objective_records if value >= best_seen - 1e-12]
        last_best_iter = max(best_iters) if best_iters else 0
        return max(0, int(iteration) - int(last_best_iter))

    @staticmethod
    def _best_so_far_improvement(records: list[dict[str, Any]]) -> float:
        by_iter: dict[int, float] = {}
        for idx, r in enumerate(records):
            if r.get("objective") is None:
                continue
            it = int(r.get("iteration", idx))
            by_iter[it] = max(by_iter.get(it, float("-inf")), float(r["objective"]))
        if len(by_iter) < 2:
            return 0.0
        vals = [by_iter[k] for k in sorted(by_iter)]
        best = vals[0]
        history = []
        for v in vals:
            best = max(best, v)
            history.append(best)
        if len(history) < 2 or abs(history[-2]) < 1e-12:
            return 0.0
        return (history[-1] - history[-2]) / abs(history[-2])

    @staticmethod
    def _diversity(records: list[dict[str, Any]]) -> float:
        if not records:
            return 0.0
        keys = [tuple(sorted((r.get("parameters") or {}).items())) for r in records[-10:]]
        return len(set(keys)) / len(keys)
