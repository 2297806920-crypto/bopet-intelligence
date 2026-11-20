# -*- coding: utf-8 -*-
"""Four-part evaluation, with explicit N/A semantics."""

from __future__ import annotations

import streamlit as st

from ui.components import kpi_row
from ui.data import latest_full_summary
from ui.theme import fmt, page_header, pct, section, source_note


def _result():
    return st.session_state.get("optimization_summary")


def _card(title: str, rows: list[tuple[str, object]], note: str = "") -> None:
    with st.container(border=True):
        section(title)
        for label, value in rows:
            st.markdown(f"**{label}** · {value}")
        if note:
            st.caption(note)


def render(demo: bool = False) -> None:
    summary = _result()
    if summary is None and demo:
        summary = latest_full_summary()
    page_header(
        "Multi-dimensional evaluation",
        "Physical, production, economic and uncertainty results from the same candidate.",
        kicker="WORKSPACE 05 · EVALUATION",
    )
    if summary is None:
        st.caption("Run an optimization first. The evaluation page reads the engine result, not a separate mock.")
        return

    ev = summary.get("best_evaluation") or {}
    physical = ev.get("physical_result") or {}
    production = ev.get("production_result") or {}
    economic = ev.get("economic_result") or {}
    uncertainty = ev.get("uncertainty_result") or {}
    metrics = production.get("metrics") or {}

    st.caption(f"run `{summary.get('run_id')}` · candidate `{(summary.get('best_candidate') or {}).get('candidate_id', 'N/A')}` · "
               f"version `{ev.get('evaluation_version', 'N/A')}`")

    kpi_row([
        {"label": "Hard feasible", "value": "YES" if ev.get("hard_feasible") else "NO",
         "help": "Hard constraint result; UNKNOWN is never converted to PASS."},
        {"label": "Soft penalty", "value": fmt(ev.get("soft_penalty"), 4)},
        {"label": "Qualified output t", "value": fmt(metrics.get("qualified_t"), 1)},
        {"label": "Annual net benefit", "value": fmt(economic.get("annual_net_benefit"), 0)},
        {"label": "Uncertainty", "value": fmt(uncertainty.get("uncertainty"), 3)},
    ])

    left, right = st.columns(2, gap="medium")
    with left:
        _card("Physical feasibility", [
            ("Hard feasible", "YES" if physical.get("hard_feasible") else "NO"),
            ("Capex wan", fmt(physical.get("capex_wan"), 1)),
            ("Install h", fmt(physical.get("install_h"), 1)),
            ("Missing fields", ", ".join(physical.get("missing_fields") or []) or "none"),
        ], "Physical precheck is not a full 24-variable mass balance.")
        _card("Production performance", [
            ("Quality yield", pct(metrics.get("quality_yield"))),
            ("Demand fill", pct(metrics.get("demand_fill"))),
            ("Downtime h", fmt(metrics.get("downtime_h"), 1)),
            ("Transition h", fmt(metrics.get("transition_h"), 1)),
            ("Unit cost", fmt(metrics.get("unit_cost"), 2)),
        ], production.get("double_counting_check", "Engineering estimate."))
    with right:
        _card("Economic value", [
            ("Monthly gain after amortization", fmt(economic.get("monthly_gain_after_amortization"), 0)),
            ("Annual net benefit", fmt(economic.get("annual_net_benefit"), 0)),
            ("Payback months (cash basis)", fmt(economic.get("payback_months_cash_basis"), 2)),
            ("Capex amortization / month", fmt(economic.get("capex_monthly_amortization"), 0)),
        ], economic.get("double_counting_warning", ""))
        _card("Uncertainty assessment", [
            ("Uncertainty", fmt(uncertainty.get("uncertainty"), 3)),
            ("Missing ratio", pct(uncertainty.get("missing_ratio"))),
            ("Uncalibrated ratio", pct(uncertainty.get("uncalibrated_ratio"))),
            ("ci95", "N/A" if uncertainty.get("ci95") is None else str(uncertainty.get("ci95"))),
        ], "Information risk is not a statistical confidence interval. ci95 is N/A when not estimated.")

    with st.container(border=True):
        section("Constraint status", "Latest candidate only.")
        report = physical.get("constraint_report") or {}
        rows = [
            {"check": "budget", "status": "PASS" if report.get("budget_ok") else "FAIL"},
            {"check": "install window", "status": "PASS" if report.get("install_ok") else "FAIL"},
            {"check": "single shutdown", "status": "PASS" if report.get("single_ok") else "FAIL"},
            {"check": "hard failures", "status": ", ".join(report.get("hard_failures") or []) or "none"},
        ]
        st.dataframe(rows, hide_index=True, width="stretch",
                     alt="Constraint checks for the latest candidate")

    with st.expander("Raw evaluator payloads", expanded=False):
        st.caption("Values are shown as returned; null remains null.")
        st.json({
            "physical": physical,
            "production": production.get("metrics") or {},
            "economic": economic,
            "uncertainty": uncertainty,
        }, expanded=False)
    source_note("evaluators/pipeline.py · production_model.py · not a plant measurement")
