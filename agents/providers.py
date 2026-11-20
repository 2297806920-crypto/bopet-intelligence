# -*- coding: utf-8 -*-
"""Replaceable LLM providers. No endpoint or model is invented."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from core.schemas import Strategy


class ProviderUnavailable(RuntimeError):
    pass


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, action: str = "EXPLORE"):
        self.action = action

    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"action": self.action, "reason": "mock provider for tests", "candidate_count": 2}


class RuleBasedProvider(LLMProvider):
    name = "rule"

    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        labels = set(context.get("state_labels") or [])
        if "CONSTRAINT_CONFLICT" in labels or "HARD_CONSTRAINT_VIOLATION" in labels:
            return {"action": "REPAIR", "reason": "hard constraint issue", "search_step": 0.08,
                    "exploration_ratio": 0.0, "candidate_count": 2}
        if "HIGH_UNCERTAINTY" in labels:
            return {"action": "UNCERTAINTY_REDUCTION", "reason": "uncertainty high",
                    "exploration_ratio": 0.5, "candidate_count": 2}
        if "STAGNATION" in labels:
            no_improve = int(context.get("no_improvement_rounds") or 0)
            if no_improve < 4:
                return {"action": "LOCAL_REFINE", "reason": "stagnation; refine best neighborhood",
                        "search_step": 0.06, "exploration_ratio": 0.0, "candidate_count": 2}
            return {"action": "DIVERSIFY", "reason": "long stagnation; restore diversity",
                    "search_step": 0.30, "exploration_ratio": 0.85, "candidate_count": 3}
        if "IMPROVING" in labels:
            return {"action": "EXPLOIT", "reason": "improving", "search_step": 0.10,
                    "exploration_ratio": 0.15, "candidate_count": 2}
        return {"action": "EXPLORE", "reason": "default exploration", "search_step": 0.20,
                "exploration_ratio": 0.60, "candidate_count": 2}


class SiliconFlowProvider(LLMProvider):
    """OpenAI-compatible provider; endpoint/model must come from env/config."""

    name = "siliconflow"

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None, timeout: float = 30.0, max_retries: int = 1):
        self.base_url = base_url or os.getenv("LLM_BASE_URL") or ""
        self.model = model or os.getenv("LLM_MODEL") or ""
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("SILICONFLOW_API_KEY") or ""
        self.timeout = float(os.getenv("LLM_TIMEOUT", timeout))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", max_retries))
        if not (self.base_url and self.model and self.api_key):
            raise ProviderUnavailable("LLM_BASE_URL, LLM_MODEL and LLM_API_KEY are required")

    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                        timeout=self.timeout, max_retries=self.max_retries)
        prompt = (
            "You are a search controller for an industrial optimizer. "
            "Return only JSON with one action from EXPLORE, EXPLOIT, REPAIR, "
            "CONSTRAINT_FOCUSED, UNCERTAINTY_REDUCTION, LOCAL_REFINE, DIVERSIFY, STOP. "
            "Never change safety bounds. Context: "
            + json.dumps(context, ensure_ascii=False)
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.choices[0].message.content or ""
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(content)


class InternLMProvider(LLMProvider):
    """书生/InternLM OpenAI-compatible provider.

    The Base URL shown by the 书生/InternLM console is used as the default;
    the model name MUST be supplied via INTERNLM_MODEL or LLM_MODEL. No model
    name or API key is invented.
    """

    name = "internlm"
    DEFAULT_BASE_URL = "https://discovery-api.intern-ai.org.cn/v1"

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None, timeout: float = 30.0, max_retries: int = 1):
        self.base_url = (base_url or os.getenv("INTERNLM_BASE_URL")
                         or os.getenv("LLM_BASE_URL") or self.DEFAULT_BASE_URL)
        self.model = model or os.getenv("INTERNLM_MODEL") or os.getenv("LLM_MODEL") or ""
        self.api_key = (api_key or os.getenv("INTERNLM_API_KEY")
                        or os.getenv("LLM_API_KEY") or os.getenv("SHUSHENG_API_KEY") or "")
        self.timeout = float(os.getenv("LLM_TIMEOUT", timeout))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", max_retries))
        if not (self.model and self.api_key):
            raise ProviderUnavailable(
                "书生/InternLM requires INTERNLM_MODEL (or LLM_MODEL) and "
                "INTERNLM_API_KEY (or LLM_API_KEY)"
            )

    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                        timeout=self.timeout, max_retries=self.max_retries)
        prompt = (
            "You are a search controller for an industrial optimizer. "
            "Return only JSON with one action from EXPLORE, EXPLOIT, REPAIR, "
            "CONSTRAINT_FOCUSED, UNCERTAINTY_REDUCTION, LOCAL_REFINE, DIVERSIFY, STOP. "
            "Never change safety bounds. Context: "
            + json.dumps(context, ensure_ascii=False)
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.choices[0].message.content or ""
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(content)


def get_provider(name: str | None = None) -> LLMProvider:
    provider = (name or os.getenv("LLM_PROVIDER") or "rule").strip().lower()
    if provider in ("rule", "rulebased", "rule_based"):
        return RuleBasedProvider()
    if provider == "mock":
        return MockProvider()
    if provider in ("siliconflow", "openai"):
        try:
            return SiliconFlowProvider()
        except ProviderUnavailable:
            return RuleBasedProvider()
    if provider in ("internlm", "shusheng"):
        return InternLMProvider()
    return RuleBasedProvider()


ALLOWED_ACTIONS = {s.value for s in Strategy}
