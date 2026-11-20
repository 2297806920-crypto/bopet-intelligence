# -*- coding: utf-8 -*-
"""Overview: capability and system state, driven by real artifacts."""

from __future__ import annotations

import re

import streamlit as st

from core.physics import FORMULAS
from scenarios.bopet import BOPET_VARIABLES
from services.evidence_catalog import catalog_stats
from ui.components import flow, kpi_row
from ui.data import audit_counts, db_snapshot, experiment_summary, latest_run, test_count
from ui.theme import fmt, page_header, section, source_note


def _open_optimization() -> None:
    st.session_state["nav"] = "04  智能优化"


def render(demo: bool = False) -> None:
    db = db_snapshot()
    stats = catalog_stats() if db.get("exists") else {"total_evidence_rows": 0, "distinct_papers": 0}
    counts = audit_counts() or {}
    has_hard = sum(1 for v in BOPET_VARIABLES if str(v.constraint_type) == "HARD")
    latest = latest_run()
    tests = test_count()
    test_match = re.search(r"\d+", tests)
    test_value = test_match.group(0) if test_match else "N/A"

    page_header(
        "BOPET Intelligence",
        "Evidence-constrained optimization workspace for industrial process decisions",
        kicker="WORKSPACE 01 · OVERVIEW",
    )
    st.caption(
        f"V3.0 · mode {'DEMO replay' if demo else 'live/offline'} · "
        f"database {'connected' if db.get('exists') else 'unavailable'} · "
        f"evidence {stats.get('distinct_papers', 0):,} papers"
    )
    st.space("small")

    kpi_row([
        {"label": "Evidence rows", "value": f"{stats.get('total_evidence_rows', 0):,}",
         "help": "Read-only rows in the two evidence tables."},
        {"label": "Distinct papers", "value": f"{stats.get('distinct_papers', 0):,}",
         "help": "Distinct paper IDs across evidence tables."},
        {"label": "Decision variables", "value": str(len(BOPET_VARIABLES)),
         "help": "BOPET 24-variable scenario definition."},
        {"label": "Hard constraints", "value": str(has_hard),
         "help": "Variables with HARD constraint type."},
        {"label": "Formula library", "value": str(len(FORMULAS)),
         "help": "Implemented F01–F07 relationships."},
        {"label": "Automated tests", "value": test_value,
         "help": "Latest pytest collection record; not a live test."},
    ])

    st.space("small")
    with st.container(border=True):
        section("System chain", "Evidence first; optimization is downstream of constraints.")
        flow([
            ("证据知识库", "SQLite evidence catalog"),
            ("数理约束", "hard / soft / performance / UNKNOWN"),
            ("多维评价", "physical / production / economic / uncertainty"),
            ("Agent 决策", "state labels and operator policy"),
            ("优化搜索", "UCB / local / repair / diversify"),
            ("工程审核", "human review, local audit only"),
        ])
        source_note("module map: services/evidence_catalog.py → core/constraints.py → evaluators/pipeline.py → agents/controller.py")

    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        with st.container(border=True):
            section("Latest optimization run", "Loaded from outputs/v3_runs, not a live metric.")
            if latest:
                st.markdown(f"**{latest['run_id']}**")
                st.caption(f"{latest['scenario']} · seed {latest['seed']} · {latest['data_mode']}")
                st.metric("Best objective", fmt(latest["best_objective"]),
                          help="Objective value stored in the latest summary.json")
                st.caption(
                    f"{latest['evaluations']} evaluations · {latest['iterations']} iterations · "
                    f"stop: {latest['stop_reason']} · {latest['elapsed_s']} s"
                )
                st.caption(f"source: {latest['path']}")
            else:
                st.caption("No saved optimization run found.")
            st.button("Open optimization console", type="primary",
                      icon=":material/arrow_forward:", on_click=_open_optimization)

    with right:
        with st.container(border=True):
            section("Experiment snapshot", "Latest saved comparison summary; three seeds is preliminary.")
            summary = experiment_summary()
            if summary:
                preview = []
                for key, item in list(summary.items())[:8]:
                    if not isinstance(item, dict):
                        continue
                    preview.append({
                        "case": key,
                        "n": item.get("n"),
                        "mean": round(item.get("mean", 0), 4) if isinstance(item.get("mean"), (int, float)) else item.get("mean"),
                        "std": round(item.get("std", 0), 4) if isinstance(item.get("std"), (int, float)) else item.get("std"),
                    })
                st.dataframe(preview, hide_index=True, width="stretch",
                             alt="Latest experiment summary: case, sample count, mean and standard deviation")
                st.caption("Not a significance test. D is not asserted to be best.")
            else:
                st.caption("No comparison summary found.")

    st.space("small")
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        with st.container(border=True):
            st.markdown("**Implemented**")
            st.caption("Evidence catalog, constraints, four-part evaluation, engine, archive, checkpoint, review log.")
            st.caption(f"A-class audit: {counts.get('A', 'N/A')}")
    with c2:
        with st.container(border=True):
            st.markdown("**Partial / bounded**")
            st.caption("Dynamic conditions are demonstrated; weights and field calibration remain bounded.")
            st.caption(f"B-class audit: {counts.get('B', 'N/A')}")
    with c3:
        with st.container(border=True):
            st.markdown("**Not implemented**")
            st.caption("PLC/MES writes, field data, production-trained prediction, formal statistical CI.")
            st.caption(f"C-class audit: {counts.get('C', 'N/A')}")
    source_note("audit: patent_audit/counts.json; test count: patent_audit/test_count.txt")
