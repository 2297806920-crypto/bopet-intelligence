# -*- coding: utf-8 -*-
"""V3.1 operator-level adaptive search.

This is deliberately separate from V3.0 AdaptiveSearch so the old algorithm
remains a baseline. Operators are selected from actual observed rewards, not
from a post-hoc narrative.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from core.schemas import AgentDecision, CandidatePlan, EvaluationResult, OptimizationState, Strategy
from optimizers.base import BaseSearch, SearchConfig


@dataclass
class OperatorStats:
    name: str
    calls: int = 0
    feasible: int = 0
    improvements: int = 0
    reward_sum: float = 0.0
    recent_rewards: list[float] = field(default_factory=list)

    def record(self, reward: float, feasible: bool, improved: bool) -> None:
        self.calls += 1
        self.feasible += int(feasible)
        self.improvements += int(improved)
        self.reward_sum += reward
        self.recent_rewards.append(reward)
        self.recent_rewards = self.recent_rewards[-20:]

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / self.calls if self.calls else 0.0

    def ucb(self, total_calls: int, c: float = 0.8) -> float:
        if self.calls == 0:
            return 1e9
        return self.mean_reward + c * math.sqrt(math.log(max(1, total_calls)) / self.calls)


class AdaptiveSearchV31(BaseSearch):
    name = "adaptive_v31"

    OPERATORS = ("random", "local", "coordinate", "diversify", "repair")

    def __init__(self, scenario, *, seed: int = 7, mode: str = "ucb"):
        super().__init__(scenario, seed=seed)
        self.mode = mode
        self.config = SearchConfig(candidate_count=1, exploration_ratio=0.0, search_step=0.1)
        self.stats = {name: OperatorStats(name) for name in self.OPERATORS}
        self.best_seen: float | None = None
        self.last_operator: str | None = None
        self._cycle = 0

    def apply_decision(self, decision: AgentDecision) -> SearchConfig:
        step = decision.search_step if decision.search_step is not None else self.config.search_step
        self.config = SearchConfig(
            search_step=min(0.5, max(0.01, float(step))),
            exploration_ratio=0.0,
            candidate_count=1,  # isolate operator effect; budget is candidate-level
            target_variables=[v for v in (decision.target_variables or []) if v in self.bounds],
            optimizer_type=self.name,
        )
        return self.config

    def _choose(self, state: OptimizationState, rng, decision: AgentDecision | None = None) -> str:
        # Cold start: one trial per operator, deterministic order.
        for name in self.OPERATORS:
            if self.stats[name].calls == 0:
                return name
        if self.mode == "llm" and decision is not None:
            action = (decision.action.value.upper() if isinstance(decision.action, Strategy)
                      else str(decision.action).upper())
            mapping = {
                "EXPLORE": "random",
                "EXPLOIT": "local",
                "LOCAL_REFINE": "coordinate",
                "DIVERSIFY": "diversify",
                "REPAIR": "repair",
                "CONSTRAINT_FOCUSED": "repair",
                "UNCERTAINTY_REDUCTION": "random",
            }
            return mapping.get(action, "random")
        if self.mode == "fixed":
            self._cycle = (self._cycle + 1) % len(self.OPERATORS)
            return self.OPERATORS[self._cycle]
        if self.mode == "history":
            return max(self.OPERATORS, key=lambda n: self.stats[n].mean_reward)
        if self.mode == "state":
            labels = set(state.state_labels)
            if "HARD_CONSTRAINT_VIOLATION" in labels or "LOW_FEASIBILITY" in labels:
                return "repair"
            if "STAGNATION" in labels and state.no_improvement_rounds < 4:
                return "coordinate"
            if "HIGH_UNCERTAINTY" in labels:
                return "random"
            if "IMPROVING" in labels:
                return "local"
            return "random"
        # default UCB
        total = sum(s.calls for s in self.stats.values())
        return max(self.OPERATORS, key=lambda n: self.stats[n].ucb(total))

    def _one(self, operator: str, state: OptimizationState, rng, iteration: int) -> CandidatePlan:
        base = state.best_candidate or state.current_candidate
        step = self.config.search_step
        if operator == "random":
            return self.sample_random(rng, iteration, "random")
        if operator == "diversify":
            return self.sample_random(rng, iteration, "diversify")
        if base is None:
            return self.sample_random(rng, iteration, "random")
        if operator == "local":
            return self.sample_local(base, rng, iteration, step, "local")
        if operator == "coordinate":
            keys = list(self.bounds)
            key = rng.choice(keys)
            return self.sample_local(base, rng, iteration, step, "coordinate", variables=[key])
        if operator == "repair":
            # Project toward the known feasible best; no safety bound is changed.
            return self.sample_local(base, rng, iteration, min(step, 0.03), "repair")
        return self.sample_random(rng, iteration, "random")

    def propose(self, state: OptimizationState, decision: AgentDecision, rng) -> list[CandidatePlan]:
        self.apply_decision(decision)
        operator = self._choose(state, rng, decision)
        self.last_operator = operator
        return [self._one(operator, state, rng, state.iteration + 1)]

    def prime_best(self, value: float | None) -> None:
        if value is not None:
            self.best_seen = float(value)

    def observe(self, candidate: CandidatePlan, evaluation: EvaluationResult, accepted: bool) -> None:
        name = candidate.generation_strategy
        # generation_strategy is set to the operator name; unknown names are ignored.
        if name not in self.stats:
            return
        value = evaluation.objective_value
        previous = self.best_seen
        if value is not None:
            if previous is None:
                improvement = 0.0
            else:
                improvement = max(0.0, (float(value) - previous) / max(abs(previous), 1e-9))
            if accepted:
                self.best_seen = float(value)
        else:
            improvement = 0.0
        feasible = bool(evaluation.hard_feasible)
        reward = 0.7 * min(improvement, 1.0) + 0.2 * (1.0 if feasible else -1.0) - 0.01
        self.stats[name].record(reward, feasible, bool(accepted and improvement > 0))

    def stats_table(self) -> list[dict]:
        return [{
            "operator": s.name,
            "calls": s.calls,
            "feasible_ratio": s.feasible / s.calls if s.calls else 0.0,
            "improvements": s.improvements,
            "mean_reward": s.mean_reward,
            "total_reward": s.reward_sum,
        } for s in self.stats.values()]
