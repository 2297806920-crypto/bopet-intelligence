# -*- coding: utf-8 -*-
"""Engineering review and controlled-write demo."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import streamlit as st

import control_adapter
from services.approval_service import ApprovalService
from ui.components import kpi_row
from ui.theme import page_header, section, source_note

APPROVAL_PATH = Path(__file__).resolve().parents[2] / "data" / "review" / "approvals.jsonl"


def render(legacy_control: Callable[[], None]) -> None:
    page_header(
        "Engineering review",
        "Human review, change visibility, and local audit. No PLC/MES connection.",
        kicker="WORKSPACE 07 · REVIEW",
    )
    latest = ApprovalService(APPROVAL_PATH).latest()
    state = control_adapter.get_state()
    kpi_row([
        {"label": "Write mode", "value": control_adapter.MODE,
         "help": "Local audit-log demo only."},
        {"label": "PLC/MES", "value": "Disconnected"},
        {"label": "Latest decision", "value": (latest or {}).get("decision", "N/A")},
        {"label": "Reviewer", "value": (latest or {}).get("reviewer", "N/A")},
    ])
    st.warning(
        "Controlled write is a local demonstration. It cannot approve itself, change safety bounds, "
        "or write to plant equipment.",
        icon=":material/shield:",
    )

    with st.container(border=True):
        section("Change list", "Only the five demo-writable setpoints are shown.")
        rows = []
        for key, meta in control_adapter.PARAMETERS.items():
            current = state.get(key)
            baseline = meta["baseline"]
            rows.append({
                "parameter": meta["label"],
                "unit": meta["unit"],
                "baseline": baseline,
                "current": current,
                "delta": round(float(current) - float(baseline), 4) if current is not None else None,
                "max delta": meta["max_delta"],
                "evidence": meta["evidence"],
            })
        st.dataframe(rows, hide_index=True, width="stretch",
                     alt="Controlled setpoints with baseline, current value, delta and evidence")

    with st.container(border=True):
        section("Review record", "Latest local audit entry; approval is not a plant write.")
        if latest:
            st.caption(f"{latest.get('timestamp')} · {latest.get('reviewer')} · {latest.get('decision')}")
            st.json({
                "hard_feasible": latest.get("hard_feasible"),
                "missing_fields": latest.get("missing_fields"),
                "data_mode": latest.get("data_mode"),
                "llm_approved": latest.get("llm_approved"),
                "plant_write": latest.get("plant_write"),
                "note": latest.get("note"),
            }, expanded=False)
        else:
            st.caption("No review record yet.")

    with st.expander("Controlled-write workspace (existing business function)", expanded=True):
        legacy_control()
    source_note("services/approval_service.py · control_adapter.py · local JSON/JSONL audit only")
