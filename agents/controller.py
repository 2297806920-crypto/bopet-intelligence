# -*- coding: utf-8 -*-
"""Deterministic controller with optional LLM proposal and hard fallback."""

from __future__ import annotations

from typing import Any

from agents.providers import LLMProvider, RuleBasedProvider
from core.schemas import AgentDecision, OptimizationState, Strategy

DEFAULT_PARAMS = {
    "EXPLORE": (0.20, 0.60, 2),
    "EXPLOIT": (0.10, 0.15, 2),
    "REPAIR": (0.08, 0.00, 2),
    "CONSTRAINT_FOCUSED": (0.05, 0.00, 2),
    "UNCERTAINTY_REDUCTION": (0.15, 0.50, 2),
    "LOCAL_REFINE": (0.06, 0.00, 2),
    "DIVERSIFY": (0.30, 0.85, 3),
    "STOP": (0.0, 0.0, 1),
}


class AgentController:
    def __init__(self, provider: LLMProvider | None = None):
        self.rule = RuleBasedProvider()
        self.provider = provider

    def decide(self, state: OptimizationState) -> AgentDecision:
        context = {
            "iteration": state.iteration,
            "state_labels": state.state_labels,
            "feasible_ratio": state.feasible_candidate_ratio,
            "hard_violation_frequency": state.hard_violation_frequency,
            "no_improvement_rounds": state.no_improvement_rounds,
            "soft_penalty": state.soft_penalty_trend[-1] if state.soft_penalty_trend else 0.0,
            "uncertainty": state.uncertainty_trend[-1] if state.uncertainty_trend else 0.0,
        }
        raw: dict[str, Any] | None = None
        if self.provider is not None:
            try:
                raw = self.provider.decide(context)
            except Exception:
                raw = None
        if raw is None:
            raw = self.rule.decide(context)
        return self._validate(raw, context)

    def _validate(self, raw: dict[str, Any], context: dict[str, Any]) -> AgentDecision:
        action_raw = str(raw.get("action", "EXPLORE")).strip().upper()
        if action_raw not in {s.value for s in Strategy}:
            raw = self.rule.decide(context)
            action_raw = str(raw.get("action", "EXPLORE")).upper()
        action = Strategy(action_raw)
        if action == Strategy.STOP:
            return AgentDecision(action=action, reason=str(raw.get("reason", "stop")),
                                 state_labels=context["state_labels"], stopping_reason="agent stop")
        step, explore, count = DEFAULT_PARAMS[action.value]
        try:
            step = float(raw.get("search_step", step))
            explore = float(raw.get("exploration_ratio", explore))
            count = int(raw.get("candidate_count", count))
        except (TypeError, ValueError):
            raw = self.rule.decide(context)
            action = Strategy(str(raw.get("action", "EXPLORE")).upper())
            step, explore, count = DEFAULT_PARAMS[action.value]
        return AgentDecision(
            action=action,
            reason=str(raw.get("reason", "")),
            state_labels=context["state_labels"],
            target_variables=[str(v) for v in raw.get("target_variables", []) if isinstance(v, str)],
            search_step=min(0.5, max(0.01, step)),
            exploration_ratio=min(1.0, max(0.0, explore)),
            candidate_count=min(8, max(1, count)),
            required_information=list(raw.get("required_information", [])),
        )
