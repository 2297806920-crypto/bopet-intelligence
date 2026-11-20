# -*- coding: utf-8 -*-
"""Agent optimization console with real engine output only."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from agents.controller import AgentController
from agents.providers import get_provider
from optimizers.adaptive_v31 import AdaptiveSearchV31
from optimizers.differential_evolution import DifferentialEvolutionSearch
from optimizers.fixed_schedule import FixedScheduleSearch
from optimizers.random_search import FixedLocalSearch
from scenarios.benchmark import BenchmarkScenario
from scenarios.bopet_measures import BOPETMeasureScenario
from scenarios.bopet_process import BOPETProcessScenario
from services.optimization_engine import EngineConfig, OptimizationEngine
from ui.components import kpi_row
from ui.data import latest_full_summary
from ui.theme import fmt, page_header, pct, section, source_note

ROOT = Path(__file__).resolve().parents[2]

SCENARIOS = {
    "BOPET measures (M1–M7)": BOPETMeasureScenario,
    "BOPET 24-variable proxy": BOPETProcessScenario,
    "Benchmark": BenchmarkScenario,
}
ALGORITHMS = {
    "E · UCB adaptive": "ucb",
    "B · fixed local": "local",
    "C · fixed schedule": "schedule",
    "F · differential evolution": "de",
}


def _summary() -> dict | None:
    return st.session_state.get("optimization_summary")


def _reset() -> None:
    st.session_state.pop("optimization_summary", None)


def _load_demo() -> dict | None:
    return latest_full_summary()


def _last_decision(summary: dict) -> tuple[dict, dict]:
    out = Path(summary.get("output_dir", "")) / "rounds.jsonl"
    state, decision = {}, {}
    if not out.exists():
        return state, decision
    try:
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "state" in item:
                state = item["state"] or {}
            if "decision" in item:
                decision = item["decision"] or {}
    except OSError:
        pass
    return state, decision


def _build_search(kind: str, scenario, seed: int):
    if kind == "ucb":
        return AdaptiveSearchV31(scenario, seed=seed, mode="ucb")
    if kind == "local":
        return FixedLocalSearch(scenario, seed=seed)
    if kind == "schedule":
        return FixedScheduleSearch(scenario, seed=seed)
    return DifferentialEvolutionSearch(scenario, seed=seed)


def _history_frame(summary: dict) -> pd.DataFrame:
    records = summary.get("records") or []
    rows = []
    best = None
    for index, r in enumerate(records):
        obj = r.get("objective")
        if obj is not None and (best is None or obj > best):
            best = obj
        rows.append({
            "candidate": index,
            "current": obj,
            "best_so_far": best,
            "soft_penalty": r.get("soft_penalty"),
            "hard_feasible": r.get("hard_feasible"),
            "strategy": r.get("strategy"),
            "action": r.get("control_action"),
        })
    return pd.DataFrame(rows)


def _render_charts(summary: dict) -> None:
    df = _history_frame(summary)
    records = summary.get("records") or []
    baseline = records[0].get("objective") if records else None
    feasible = [r.get("hard_feasible") for r in records if r.get("hard_feasible") is not None]
    last = records[-1] if records else {}
    kpi_row([
        {"label": "Evaluations", "value": f"{summary.get('candidates_evaluated', 0):,}"},
        {"label": "Iterations", "value": f"{summary.get('iterations', 0):,}"},
        {"label": "Feasible ratio", "value": pct(sum(feasible) / len(feasible)) if feasible else "N/A"},
        {"label": "Best objective", "value": fmt((summary.get("best_evaluation") or {}).get("objective_value"))},
    ])
    st.caption(f"stop: {summary.get('stop_reason', 'N/A')} · seed: {summary.get('seed', 'N/A')}")
    if df.empty:
        st.caption("No candidate records in this run.")
        return

    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        with st.container(border=True):
            section("Convergence", "Best-so-far and current candidate; baseline is the first stored record.")
            chart = df.set_index("candidate")[["current", "best_so_far"]].copy()
            if baseline is not None:
                chart["baseline"] = float(baseline)
            st.line_chart(chart, height=300, width="stretch",
                          alt="Best-so-far and current objective by candidate, with baseline reference")
            st.caption(f"baseline objective: {fmt(baseline)} · current: {fmt(last.get('objective'))}")
        with st.container(border=True):
            section("Feasibility and penalty", "Hard-feasibility is a constraint result, not a quality score.")
            aux = df.set_index("candidate")[["soft_penalty"]].copy()
            aux["hard_feasible"] = df.set_index("candidate")["hard_feasible"].astype(float)
            st.line_chart(aux, height=180, width="stretch",
                          alt="Soft penalty and hard feasibility indicator by candidate")
    with right:
        with st.container(border=True):
            section("Decision panel", "Latest agent decision from the run log.")
            state, decision = _last_decision(summary)
            labels = ", ".join(state.get("state_labels") or []) or "N/A"
            st.markdown(f"**Iteration** `{state.get('iteration', 'N/A')}`")
            st.markdown(f"**State** {labels}")
            st.markdown(f"**Action** `{decision.get('action', 'N/A')}`")
            st.markdown(f"**Strategy** `{last.get('strategy', 'N/A')}`")
            st.markdown(f"**Search step** `{fmt(decision.get('search_step'), 3)}`")
            st.markdown(f"**Exploration** `{fmt(decision.get('exploration_ratio'), 3)}`")
            st.markdown(f"**Candidates** `{decision.get('candidate_count', 'N/A')}`")
            st.caption(decision.get("reason") or "No model reason recorded for this run.")
            failures = (((last.get("evaluation") or {}).get("physical_result") or {})
                        .get("constraint_report") or {}).get("hard_failures") or []
            if failures:
                st.warning("Hard failures: " + ", ".join(map(str, failures)))
            else:
                st.caption("Hard failures: none on latest candidate.")
        st.caption("The engine is synchronous; no fake stop button is shown.")

    with st.container(border=True):
        section("Strategy timeline", "Actual operator and controller action, not a replay animation.")
        timeline = df[["candidate", "strategy", "action", "hard_feasible"]].tail(20)
        st.dataframe(timeline, hide_index=True, width="stretch",
                     alt="Recent strategy and controller action timeline")


def _render_best(summary: dict) -> None:
    records = summary.get("records") or []
    best_candidate = summary.get("best_candidate") or {}
    best_eval = summary.get("best_evaluation") or {}
    baseline_params = records[0].get("parameters", {}) if records else {}
    best_params = best_candidate.get("parameters", {}) or {}
    with st.container(border=True):
        section("Best candidate", "Stored by the anti-regression archive; no post-hoc selection.")
        st.caption(f"candidate `{best_candidate.get('candidate_id', 'N/A')}` · objective {fmt(best_eval.get('objective_value'))}")
        rows = []
        for key in sorted(set(baseline_params) | set(best_params)):
            b = baseline_params.get(key)
            v = best_params.get(key)
            delta = None
            if isinstance(b, (int, float)) and isinstance(v, (int, float)):
                delta = v - b
            rows.append({"parameter": key, "baseline": b, "best": v, "delta": delta})
        st.dataframe(rows, hide_index=True, width="stretch",
                     alt="Best candidate parameters compared with the baseline")
    with st.expander("Round log and export", expanded=False):
        logs = pd.DataFrame(records)
        if not logs.empty:
            keep = [c for c in ("iteration", "candidate_id", "strategy", "control_action",
                                "search_step", "exploration_ratio", "objective",
                                "hard_feasible", "soft_penalty", "accepted_as_best") if c in logs]
            st.dataframe(logs[keep], hide_index=True, width="stretch",
                         alt="Round-level optimization log")
        st.download_button(
            "Download full run report (JSON)",
            data=json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"{summary.get('run_id', 'run')}.json",
            mime="application/json",
            icon=":material/download:",
        )
        st.caption(f"source: {summary.get('output_dir', 'N/A')}")


def render(demo: bool = False, legacy_plan=None) -> None:
    page_header(
        "Agent optimization",
        "Run the real engine, inspect its decisions, and export the evidence trace.",
        kicker="WORKSPACE 04 · OPTIMIZATION",
    )
    with st.container(border=True):
        section("Run controls", "No API key required for rule mode. No safe interruption is exposed.")
        with st.form("optimization_form"):
            c1, c2, c3 = st.columns([1.5, 1, 1])
            scenario_name = c1.selectbox("Scenario", list(SCENARIOS), key="opt_scenario")
            algorithm_name = c2.selectbox("Algorithm", list(ALGORITHMS), key="opt_algorithm")
            provider_name = c3.selectbox("Provider", ["rule", "internlm"], key="opt_provider",
                                         help="internlm uses LLM_MODEL / INTERNLM_API_KEY; no key is stored in the page.")
            c4, c5, c6 = st.columns([1, 1, 1])
            budget = c4.number_input("Evaluations", min_value=5, max_value=120, value=20, step=5,
                                     key="opt_budget")
            seed = c5.number_input("Seed", min_value=1, max_value=9999, value=7, key="opt_seed")
            tolerance = c6.number_input("Patience", min_value=1, max_value=60, value=20,
                                        key="opt_patience")
            submitted = st.form_submit_button("Run optimization", type="primary", width="stretch")

    if submitted:
        scenario = SCENARIOS[scenario_name]()
        controller = AgentController()
        provider_note = "rule"
        if provider_name == "internlm":
            try:
                controller = AgentController(get_provider("internlm"))
                provider_note = "internlm"
            except Exception as exc:
                st.warning(f"Model provider unavailable; using rule controller: {exc}",
                           icon=":material/key_off:")
        search = _build_search(ALGORITHMS[algorithm_name], scenario, int(seed))
        engine = OptimizationEngine(
            scenario, search, controller,
            config=EngineConfig(max_iterations=int(budget), max_evaluations=int(budget),
                                seed=int(seed), patience=int(tolerance),
                                output_dir=ROOT / "outputs" / "v3_runs"),
        )
        with st.spinner("Running the real optimization engine..."):
            st.session_state["optimization_summary"] = engine.run()
        st.success(f"Run completed with {provider_note} controller.", icon=":material/check_circle:")

    summary = _summary()
    if demo and summary is None:
        summary = _load_demo()
        if summary:
            st.info("Demo replay: showing the latest saved v3 run. It is not a new live run.",
                    icon=":material/history:")
    if summary is None:
        st.caption("No run selected. Configure a run above, or enable demo mode in the sidebar.")
        return

    st.caption(f"run `{summary.get('run_id', 'N/A')}` · scenario `{summary.get('scenario', 'N/A')}` · "
               f"mode `{summary.get('data_mode', 'N/A')}` · seed `{summary.get('seed', 'N/A')}`")
    _render_charts(summary)
    _render_best(summary)
    st.button("Clear current result", icon=":material/refresh:", on_click=_reset)
    if legacy_plan is not None:
        with st.expander("Original M1–M7 plan loop (compatibility entry)", expanded=False):
            st.caption("The original plan-feedback loop is preserved here; its results are separate from the V3 engine run above.")
            legacy_plan()
    source_note("services/optimization_engine.py · outputs/v3_runs/<run>/summary.json · not real-time")
