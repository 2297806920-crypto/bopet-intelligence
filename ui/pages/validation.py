# -*- coding: utf-8 -*-
"""Validation workspace: real saved experiments, no invented significance."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ui.data import experiment_summary
from ui.theme import fmt, page_header, section, source_note

ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = ROOT / "outputs" / "v31_experiments"
ABLATION = ROOT / "outputs" / "v3_ablation" / "ablation_summary.json"


@st.cache_data(show_spinner=False)
def _csv() -> pd.DataFrame:
    path = EXP_DIR / "optimizer_comparison.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


@st.cache_data(show_spinner=False)
def _curves(scenario: str, seed: int, methods: tuple[str, ...]) -> pd.DataFrame:
    df = _csv()
    if df.empty:
        return pd.DataFrame()
    rows = []
    for method in methods:
        match = df[(df["scenario"] == scenario) & (df["method"] == method) & (df["seed"] == seed)]
        if match.empty:
            continue
        run_id = str(match.iloc[0]["run_id"])
        log = EXP_DIR / "runs" / run_id / "rounds.jsonl"
        if not log.exists():
            continue
        best = None
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "candidate_id" not in rec:
                continue
            obj = rec.get("objective")
            if obj is None:
                continue
            best = obj if best is None else max(best, obj)
            rows.append({"candidate": len(rows), "method": method, "best_so_far": best})
    return pd.DataFrame(rows)


def _render_curves(df: pd.DataFrame) -> None:
    if df.empty:
        st.caption("No round-level curves available for this selection.")
        return
    pivot = df.pivot_table(index="candidate", columns="method", values="best_so_far", aggfunc="last")
    st.line_chart(pivot, height=280, width="stretch",
                  alt="Best-so-far curves by method for the selected scenario and seed")
    st.caption("Best-so-far reconstructed from saved rounds.jsonl; selected seed only.")


def render(demo: bool = False) -> None:
    page_header(
        "Validation",
        "Saved comparisons and ablations. Small samples stay labeled preliminary.",
        kicker="WORKSPACE 06 · VALIDATION",
    )
    summary = experiment_summary()
    df = _csv()
    if not summary and df.empty:
        st.caption("No experiment summary found under outputs/v31_experiments or outputs/v3_experiments.")
        return

    if not df.empty:
        scenarios = sorted(df["scenario"].unique())
        methods = sorted(df["method"].unique())
        c1, c2, c3 = st.columns([1.2, 1.4, 1])
        scenario = c1.selectbox("Scenario", scenarios, key="val_scenario")
        focus = c2.selectbox("Algorithm focus (curve)", methods,
                             index=methods.index("E_ucb") if "E_ucb" in methods else 0,
                             key="val_method")
        seeds = sorted(df[df["scenario"] == scenario]["seed"].unique())
        seed = c3.selectbox("Seed for curve", seeds, key="val_seed")
        st.caption("Experiments use a small number of seeds; no significance test is asserted.")
        filtered = df[df["scenario"] == scenario]
        with st.container(border=True):
            section("Result distribution", "Each point is one saved run; mean/std are descriptive only.")
            if summary:
                table = []
                for key, item in summary.items():
                    if "/" not in key or not isinstance(item, dict):
                        continue
                    scen, method = key.split("/", 1)
                    if scen != scenario:
                        continue
                    table.append({
                        "method": method,
                        "n": item.get("n"),
                        "mean": item.get("mean"),
                        "std": item.get("std"),
                        "best": item.get("best"),
                    })
                table = pd.DataFrame(table)
            else:
                table = filtered.groupby("method").agg(
                    n=("best_objective", "count"),
                    mean=("best_objective", "mean"),
                    std=("best_objective", "std"),
                    best=("best_objective", "max"),
                ).reset_index()
            st.dataframe(table, hide_index=True, width="stretch",
                         alt="Method comparison: sample count, mean, standard deviation and best")
            if not table.empty:
                st.bar_chart(table.set_index("method")[["mean"]], height=240, width="stretch",
                             alt="Mean best objective by method; descriptive, not a significance test")
            st.caption("D is retained as a negative result; it is not forced to look best.")
        with st.container(border=True):
            section("Convergence", "Best-so-far curves from the saved round log.")
            curves = _curves(scenario, int(seed), (focus,))
            _render_curves(curves)
        with st.container(border=True):
            section("Experiment records", "Run IDs and stop reasons are kept for audit.")
            keep = [c for c in ("scenario", "method", "seed", "best_objective", "evaluations",
                                "iterations", "stop_reason", "run_id") if c in filtered]
            st.dataframe(filtered[keep], hide_index=True, width="stretch",
                         alt="Saved experiment runs with seeds and stop reasons")

    if ABLATION.exists():
        try:
            ablation = json.loads(ABLATION.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ablation = None
        if ablation:
            with st.container(border=True):
                section("Ablation", "Existing ablation artifact; no new runs are fabricated.")
                rows = []
                for key, item in ablation.items():
                    if isinstance(item, dict):
                        rows.append({"variant": key, **{k: item.get(k) for k in ("mean", "std", "n", "best") if k in item}})
                st.dataframe(rows, hide_index=True, width="stretch",
                             alt="Ablation variants with saved summary statistics")
    else:
        st.caption("No ablation summary found at outputs/v3_ablation/ablation_summary.json.")

    source_note("outputs/v31_experiments · outputs/v3_ablation · only saved artifacts")
