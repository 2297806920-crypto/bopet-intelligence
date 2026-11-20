# -*- coding: utf-8 -*-
"""Constraint and formula workspace over the existing 24-variable model."""

from __future__ import annotations

import streamlit as st

from core.physics import FORMULAS, PhysicsError, average_final_thickness, mass_flow
from scenarios.bopet import BOPET_VARIABLES
from ui.components import kpi_row
from ui.theme import page_header, section, source_note


def _latex(expr: str) -> str:
    replacements = {
        "m_dot": r"\dot{m}", "rho": r"\rho", "lambda_MD": r"\lambda_{MD}",
        "lambda_TD": r"\lambda_{TD}", "h_final": r"h_{final}", "h_cast": r"h_{cast}",
        "*": r" \cdot ", "/": r" / ", "rho_cast": r"\rho_{cast}", "rho_final": r"\rho_{final}",
    }
    out = expr
    for key in sorted(replacements, key=len, reverse=True):
        out = out.replace(key, replacements[key])
    return out


def render() -> None:
    counts = {"HARD": 0, "SOFT": 0, "PERFORMANCE": 0, "DERIVED": 0}
    uncalibrated = 0
    for v in BOPET_VARIABLES:
        counts[str(v.constraint_type)] = counts.get(str(v.constraint_type), 0) + 1
        if str(v.calibration_status) != "CALIBRATED":
            uncalibrated += 1

    page_header(
        "Mathematical constraints",
        "Twenty-four decisions with explicit bounds, calibration state and evidence links.",
        kicker="WORKSPACE 03 · CONSTRAINTS",
    )
    kpi_row([
        {"label": "Hard constraints", "value": str(counts["HARD"])},
        {"label": "Soft constraints", "value": str(counts["SOFT"])},
        {"label": "Performance windows", "value": str(counts["PERFORMANCE"])},
        {"label": "Derived variables", "value": str(counts["DERIVED"])},
        {"label": "Uncalibrated", "value": str(uncalibrated)},
    ])

    with st.container(border=True):
        section("Decision variables", "Select a row in the table to inspect its full definition.")
        table = [{
            "ID": v.variable_id,
            "Name": v.name,
            "Symbol": v.symbol,
            "Unit": v.unit or "—",
            "Lower": v.lower_bound,
            "Upper": v.upper_bound,
            "Preferred": f"{v.preferred_range[0]} – {v.preferred_range[1]}" if v.preferred_range else "—",
            "Type": str(v.constraint_type),
            "Calibration": str(v.calibration_status),
            "Evidence": ", ".join(v.evidence_ids) or "—",
        } for v in BOPET_VARIABLES]
        st.dataframe(table, hide_index=True, width="stretch",
                     alt="BOPET decision variables with bounds, type, calibration and evidence IDs")
        source_note("scenarios/bopet.py · BOPET_VARIABLES")
        st.markdown(
            ":green-badge[PASS] :red-badge[FAIL] :orange-badge[UNKNOWN] :gray-badge[NOT APPLICABLE] "
            "— UNKNOWN is not PASS."
        )

    labels = [f"{v.variable_id} · {v.name}" for v in BOPET_VARIABLES]
    selected = st.selectbox("Variable detail", labels, key="constraint_variable")
    v = BOPET_VARIABLES[labels.index(selected)]
    left, right = st.columns([1.05, 1], gap="medium")
    with left:
        with st.container(border=True):
            section(f"{v.variable_id} · {v.name}", f"symbol `{v.symbol}`")
            st.markdown(
                f"**Bounds** `{v.lower_bound}` — `{v.upper_bound}` {v.unit or ''}  \n"
                f"**Preferred** `{v.preferred_range}`  \n"
                f"**Type** `{v.constraint_type}`  \n"
                f"**Calibration** `{v.calibration_status}`  \n"
                f"**Evidence** `{', '.join(v.evidence_ids) or 'N/A'}`"
            )
            st.json({
                "material_conditions": v.material_conditions,
                "equipment_conditions": v.equipment_conditions,
                "dependency_variables": v.dependency_variables,
                "adjustable": v.adjustable,
            }, expanded=False)
            st.caption("Applicability conditions are configuration metadata; unverified conditions are not field interlocks.")
    with right:
        with st.container(border=True):
            section("Formula library", "Only the existing F01–F07 functions are shown.")
            for fid, meta in FORMULAS.items():
                st.markdown(f"**{fid} · {meta['name']}**")
                st.code(meta["expression"], language="text")
            source_note("core/physics.py · FORMULAS")

    with st.container(border=True):
        section("Quick formula check", "Calls the existing deterministic functions; no new physics.")
        tab1, tab2 = st.tabs(["F01 mass flow", "F04 average thickness"])
        with tab1:
            c1, c2, c3, c4 = st.columns(4)
            rho = c1.number_input("Density kg/m³", value=1350.0, min_value=1.0, key="f01_rho")
            width = c2.number_input("Width m", value=1.3, min_value=0.01, key="f01_width")
            thick = c3.number_input("Thickness µm", value=12.0, min_value=0.1, key="f01_thick")
            speed = c4.number_input("Speed m/s", value=5.0, min_value=0.01, key="f01_speed")
            try:
                value = mass_flow(rho, width, thick * 1e-6, speed)
                st.metric("Mass flow kg/s", f"{value:,.6f}")
            except PhysicsError as exc:
                st.error(f"UNKNOWN: {exc}")
        with tab2:
            c1, c2, c3, c4, c5 = st.columns(5)
            h_cast = c1.number_input("Cast thickness µm", value=120.0, min_value=0.1, key="f04_h")
            rho_cast = c2.number_input("Cast density", value=1350.0, min_value=1.0, key="f04_rho_cast")
            rho_final = c3.number_input("Final density", value=1400.0, min_value=1.0, key="f04_rho_final")
            lam_md = c4.number_input("λ MD", value=3.0, min_value=1.01, key="f04_lmd")
            lam_td = c5.number_input("λ TD", value=3.2, min_value=1.01, key="f04_ltd")
            try:
                result = average_final_thickness(h_cast * 1e-6, rho_cast, rho_final, lam_md, lam_td)
                st.metric("Average final thickness µm", f"{result * 1e6:,.2f}")
                st.caption("Average estimate only; not a CD thickness profile model.")
            except PhysicsError as exc:
                st.error(f"UNKNOWN: {exc}")

    with st.expander("Formula equations", expanded=False):
        for fid, meta in FORMULAS.items():
            st.markdown(f"**{fid} · {meta['name']}**")
            st.latex(_latex(meta["expression"]))
            st.caption(f"source: {meta['source']} · tested: {meta['tested']}")
