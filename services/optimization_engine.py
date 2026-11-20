# -*- coding: utf-8 -*-
"""Single optimization orchestration entry (V3 Agent Shuttle)."""

from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.archive import AntiRegressionArchive
from core.objective import ObjectiveTerm, weighted_objective
from core.pareto_archive import ParetoArchive
from core.schemas import AgentDecision, CandidatePlan, EvaluationResult, OptimizationState, Strategy
from core.state_analyzer import StateAnalyzer
from agents.controller import AgentController
from optimizers.base import BaseSearch
from services.checkpoint import CheckpointManager


@dataclass
class EngineConfig:
    max_iterations: int = 8
    max_evaluations: int | None = None
    seed: int = 7
    patience: int = 4
    output_dir: Path = field(default_factory=lambda: Path("outputs/v3_runs"))
    run_id: str | None = None
    checkpoint_path: Path | None = None
    resume_from: Path | None = None
    archive_mode: str = "scalar"  # scalar | pareto
    pareto_directions: dict[str, str] = field(default_factory=dict)
    objective_terms: list[ObjectiveTerm] = field(default_factory=list)
    objective_version: str = "v3.1"


class OptimizationEngine:
    def __init__(self, scenario: Any, search: BaseSearch, controller: AgentController,
                 analyzer: StateAnalyzer | None = None, archive: AntiRegressionArchive | None = None,
                 config: EngineConfig | None = None):
        self.scenario = scenario
        self.search = search
        self.controller = controller
        self.analyzer = analyzer or StateAnalyzer()
        self.config = config or EngineConfig()
        version = str(getattr(scenario, "evaluation_version", "v3.0"))
        if archive is not None:
            self.archive = archive
        elif self.config.archive_mode == "pareto":
            if not self.config.pareto_directions:
                raise ValueError("pareto_directions are required for archive_mode='pareto'")
            self.archive = ParetoArchive(self.config.pareto_directions,
                                         evaluation_version=version)
        else:
            self.archive = AntiRegressionArchive(maximize=True, evaluation_version=version)

    def run(self) -> dict[str, Any]:
        resumed = False
        if self.config.resume_from is not None:
            checkpoint = CheckpointManager.load(self.config.resume_from)
            run_id = str(checkpoint["run_id"])
            records = list(checkpoint["records"])
            self.archive = AntiRegressionArchive.from_dict(checkpoint["archive"])
            state = OptimizationState.model_validate(checkpoint["state"])
            start_iteration = max(1, int(state.iteration) + 1)
            resumed = True
        else:
            run_id = self.config.run_id or datetime.now().strftime("v3_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
            records = []
            state = OptimizationState(iteration=0)
            start_iteration = 1
        out = Path(self.config.output_dir) / run_id
        out.mkdir(parents=True, exist_ok=True)
        rng = random.Random(self.config.seed)
        started = time.perf_counter()
        stop_reason = "max_iterations"

        with (out / "rounds.jsonl").open("a" if resumed else "w", encoding="utf-8") as log:
            # Seed the process/measure baseline only on a fresh run.
            initial_factory = getattr(self.scenario, "initial_candidate", None)
            if not resumed and callable(initial_factory):
                baseline = initial_factory()
                baseline_eval = self.scenario.evaluate(baseline)
                if self.config.objective_terms:
                    weighted = weighted_objective(baseline_eval.objective_vector, self.config.objective_terms)
                    if weighted["value"] is not None:
                        baseline_eval.objective_value = float(weighted["value"])
                        baseline_eval.objective_version = self.config.objective_version
                        baseline_eval.production_result["weighted_objective"] = weighted
                accepted = self.archive.consider(baseline, baseline_eval)
                record = {
                    "iteration": 0,
                    "candidate_id": baseline.candidate_id,
                    "parameters": baseline.parameters,
                    "strategy": "BASELINE",
                    "control_action": None,
                    "search_step": None,
                    "exploration_ratio": None,
                    "candidate_count": None,
                    "objective": baseline_eval.objective_value,
                    "hard_feasible": baseline_eval.hard_feasible,
                    "soft_penalty": baseline_eval.soft_penalty,
                    "uncertainty": baseline_eval.uncertainty_result.get("uncertainty", 0.0),
                    "accepted_as_best": accepted,
                    "data_mode": baseline_eval.data_mode.value if hasattr(baseline_eval.data_mode, "value") else str(baseline_eval.data_mode),
                    "evaluation": baseline_eval.model_dump(mode="json"),
                }
                records.append(record)
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()
                prime = getattr(self.search, "prime_best", None)
                if callable(prime):
                    prime(baseline_eval.objective_value)

            for iteration in range(start_iteration, self.config.max_iterations + 1):
                decision = self.controller.decide(state)
                if decision.action == Strategy.STOP:
                    stop_reason = decision.stopping_reason or "agent_stop"
                    break
                candidates = self.search.propose(state, decision, rng)
                last_candidate = None
                last_eval = None
                for candidate in candidates:
                    if self.config.max_evaluations is not None and len(records) >= self.config.max_evaluations:
                        break
                    evaluation = self.scenario.evaluate(candidate)
                    if self.config.objective_terms:
                        weighted = weighted_objective(evaluation.objective_vector, self.config.objective_terms)
                        if weighted["value"] is not None:
                            evaluation.objective_value = float(weighted["value"])
                            evaluation.objective_version = self.config.objective_version
                            evaluation.production_result["weighted_objective"] = weighted
                    accepted = self.archive.consider(candidate, evaluation)
                    observe = getattr(self.search, "observe", None)
                    if callable(observe):
                        observe(candidate, evaluation, accepted)
                    record = {
                        "iteration": iteration,
                        "candidate_id": candidate.candidate_id,
                        "parameters": candidate.parameters,
                        "strategy": candidate.generation_strategy,
                        "control_action": decision.action.value if isinstance(decision.action, Strategy) else str(decision.action),
                        "search_step": decision.search_step,
                        "exploration_ratio": decision.exploration_ratio,
                        "candidate_count": decision.candidate_count,
                        "objective": evaluation.objective_value,
                        "hard_feasible": evaluation.hard_feasible,
                        "soft_penalty": evaluation.soft_penalty,
                        "uncertainty": evaluation.uncertainty_result.get("uncertainty", 0.0),
                        "accepted_as_best": accepted,
                        "data_mode": evaluation.data_mode.value if hasattr(evaluation.data_mode, "value") else str(evaluation.data_mode),
                        "evaluation": evaluation.model_dump(mode="json"),
                    }
                    records.append(record)
                    log.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log.flush()
                    last_candidate, last_eval = candidate, evaluation

                best_obj = self.archive.best_evaluation.objective_value if self.archive.best_evaluation else None
                state = self.analyzer.analyze(records, iteration, best_obj,
                                              current_strategy=decision.action)
                state.best_candidate = self.archive.best
                state.current_candidate = last_candidate
                log.write(json.dumps({"state": state.model_dump(mode="json"), "decision": decision.model_dump(mode="json")},
                                     ensure_ascii=False) + "\n")
                log.flush()
                if self.config.checkpoint_path is not None:
                    CheckpointManager.save(
                        self.config.checkpoint_path,
                        run_id=run_id,
                        records=records,
                        archive=self.archive,
                        state=state.model_dump(mode="json"),
                        extra={"scenario": getattr(self.scenario, "name", ""),
                               "data_mode": getattr(getattr(self.scenario, "data_mode", None), "value",
                                                    str(getattr(self.scenario, "data_mode", "UNKNOWN")))},
                    )
                if self.config.max_evaluations is not None and len(records) >= self.config.max_evaluations:
                    stop_reason = "evaluation_budget"
                    break
                if state.no_improvement_rounds >= self.config.patience and iteration >= self.config.patience:
                    stop_reason = "patience"
                    break

        elapsed = time.perf_counter() - started
        summary = {
            "run_id": run_id,
            "resumed": resumed,
            "scenario": getattr(self.scenario, "name", type(self.scenario).__name__),
            "seed": self.config.seed,
            "max_evaluations": self.config.max_evaluations,
            "iterations": len({r["iteration"] for r in records}),
            "candidates_evaluated": len(records),
            "stop_reason": stop_reason,
            "elapsed_s": round(elapsed, 4),
            "best_candidate": self.archive.best.model_dump(mode="json") if self.archive.best else None,
            "best_evaluation": self.archive.best_evaluation.model_dump(mode="json") if self.archive.best_evaluation else None,
            "data_mode": getattr(getattr(self.scenario, "data_mode", None), "value", str(getattr(self.scenario, "data_mode", "UNKNOWN"))),
            "records": records,
        }
        stats = getattr(self.search, "stats_table", None)
        if callable(stats):
            summary["operator_stats"] = stats()
        if hasattr(self.archive, "front"):
            summary["pareto_front"] = [
                {"candidate_id": c.candidate_id,
                 "objective_vector": e.objective_vector,
                 "objective_value": e.objective_value}
                for c, e in self.archive.front
            ]
        (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        self.archive.save(out / "archive.json")
        summary["output_dir"] = str(out)
        return summary
