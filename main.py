# -*- coding: utf-8 -*-
"""BOPET Agent V3 command line entry.

Examples:
  python main.py --scenario benchmark --iterations 20 --seed 7
  python main.py --scenario bopet --iterations 20 --seed 7 --provider rule
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.controller import AgentController
from agents.providers import get_provider
from optimizers.adaptive_search import AdaptiveSearch
from optimizers.adaptive_v31 import AdaptiveSearchV31
from scenarios.benchmark import BenchmarkScenario
from scenarios.bopet_measures import BOPETMeasureScenario
from scenarios.bopet_process import BOPETProcessScenario
from services.optimization_engine import EngineConfig, OptimizationEngine


def build_scenario(name: str):
    if name == "benchmark":
        return BenchmarkScenario()
    if name == "bopet":
        return BOPETMeasureScenario()
    if name == "process":
        return BOPETProcessScenario()
    raise SystemExit(f"unknown scenario: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="BOPET Agent V3 adaptive optimizer")
    parser.add_argument("--scenario", choices=["benchmark", "bopet", "process"], default="bopet")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--provider", default=None, help="rule, mock, siliconflow, internlm")
    parser.add_argument("--algorithm", choices=["adaptive", "v31-ucb", "v31-state", "v31-history"],
                        default="adaptive")
    parser.add_argument("--output", default=str(ROOT / "outputs" / "v3_runs"))
    args = parser.parse_args()

    scenario = build_scenario(args.scenario)
    provider = get_provider(args.provider)
    controller = AgentController(provider)
    if args.algorithm == "adaptive":
        search = AdaptiveSearch(scenario, seed=args.seed)
    else:
        mode = args.algorithm.replace("v31-", "")
        search = AdaptiveSearchV31(scenario, seed=args.seed, mode=mode)
    engine = OptimizationEngine(
        scenario, search, controller,
        config=EngineConfig(max_iterations=args.iterations, seed=args.seed,
                            patience=args.patience, output_dir=Path(args.output)),
    )
    summary = engine.run()
    print(json.dumps({
        "run_id": summary["run_id"],
        "scenario": summary["scenario"],
        "iterations": summary["iterations"],
        "candidates_evaluated": summary["candidates_evaluated"],
        "stop_reason": summary["stop_reason"],
        "best_parameters": summary["best_candidate"]["parameters"] if summary["best_candidate"] else None,
        "best_objective": summary["best_evaluation"]["objective_value"] if summary["best_evaluation"] else None,
        "output_dir": summary["output_dir"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
