# -*- coding: utf-8 -*-
"""Method F: a compact differential-evolution baseline.

Population evaluation consumes the same evaluation budget as other methods.
This is a baseline, not a claim that DE is optimal for BOPET.
"""

from __future__ import annotations

from typing import Any

from core.schemas import AgentDecision, CandidatePlan, EvaluationResult, OptimizationState
from optimizers.base import BaseSearch


class DifferentialEvolutionSearch(BaseSearch):
    name = "de"

    def __init__(self, scenario, *, seed: int = 7, population_size: int = 8,
                 f_weight: float = 0.6, crossover: float = 0.7):
        super().__init__(scenario, seed=seed)
        self.population_size = max(4, int(population_size))
        self.f_weight = float(f_weight)
        self.crossover = float(crossover)
        self.population: list[dict[str, Any]] = []
        self.pending_target: int | None = None
        self._iteration = 0

    def _random_vector(self, rng):
        params = {}
        for key, (lo, hi) in self.bounds.items():
            value = rng.uniform(lo, hi)
            params[key] = float(round(value)) if self.discrete else value
        return params

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        self._iteration += 1
        if len(self.population) < self.population_size:
            cand = CandidatePlan(
                candidate_id=f"de-init-{self._iteration}-{rng.randrange(10**6):06d}",
                iteration=state.iteration + 1,
                parameters=self._random_vector(rng),
                generation_strategy="de-init",
                data_mode=getattr(self.scenario, "data_mode"),
            )
            self.pending_target = None
            return [cand]

        target = self._iteration % len(self.population)
        ids = [i for i in range(len(self.population)) if i != target]
        a, b, c = rng.sample(ids, 3) if len(ids) >= 3 else (ids * 3)[:3]
        base = self.population[target]["candidate"].parameters
        pa = self.population[a]["candidate"].parameters
        pb = self.population[b]["candidate"].parameters
        pc = self.population[c]["candidate"].parameters
        params = {}
        for key, (lo, hi) in self.bounds.items():
            if rng.random() < self.crossover:
                value = pa.get(key, (lo + hi) / 2) + self.f_weight * (pb.get(key, 0) - pc.get(key, 0))
                value = min(hi, max(lo, value))
            else:
                value = base.get(key, (lo + hi) / 2)
            params[key] = float(round(value)) if self.discrete else value
        self.pending_target = target
        return [CandidatePlan(
            candidate_id=f"de-trial-{self._iteration}-{rng.randrange(10**6):06d}",
            iteration=state.iteration + 1,
            parameters=params,
            generation_strategy="de-trial",
            parent_candidate_id=self.population[target]["candidate"].candidate_id,
            data_mode=getattr(self.scenario, "data_mode"),
        )]

    def observe(self, candidate: CandidatePlan, evaluation: EvaluationResult, accepted: bool) -> None:
        if candidate.generation_strategy == "de-init":
            self.population.append({"candidate": candidate, "evaluation": evaluation})
            return
        if candidate.generation_strategy == "de-trial" and self.pending_target is not None:
            target = self.population[self.pending_target]
            old = target["evaluation"].objective_value
            new = evaluation.objective_value
            better = (new is not None and evaluation.hard_feasible and
                      (old is None or (new > old)))
            if better:
                self.population[self.pending_target] = {"candidate": candidate, "evaluation": evaluation}
            self.pending_target = None
