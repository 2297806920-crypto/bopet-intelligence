# -*- coding: utf-8 -*-
"""System settings: status, versions and exports without secrets."""

from __future__ import annotations

import json

import streamlit as st

from ui.components import kpi_row
from ui.data import api_label, api_name, audit_counts, db_snapshot, latest_full_summary, test_count
from ui.theme import page_header, section, source_note


def render(legacy_database=None) -> None:
    db = db_snapshot()
    api_text, api_tone = api_label()
    counts = audit_counts() or {}
    page_header(
        "Settings",
        "Runtime status and explicit version boundaries.",
        kicker="SYSTEM 08 · SETTINGS",
    )
    kpi_row([
        {"label": "Application", "value": "V3.0 UI"},
        {"label": "Evaluation", "value": "v3.1"},
        {"label": "API", "value": "configured" if "configured" in api_text and "not" not in api_text else "not configured"},
        {"label": "Database", "value": "connected" if db.get("exists") else "unavailable"},
        {"label": "Tests", "value": test_count().split()[0] if test_count() else "N/A"},
    ])

    left, right = st.columns([1, 1], gap="medium")
    with left:
        with st.container(border=True):
            section("Runtime")
            st.markdown(f"**Database** `{db.get('path', 'N/A')}`")
            st.markdown(f"**DB status** `{'connected' if db.get('exists') else 'unavailable'}`")
            st.markdown(f"**API provider** `{api_name()}`")
            st.markdown(f"**API status** `{api_text}`")
            st.markdown("**Constraint version** `v3.0`")
            st.markdown("**Evaluation version** `v3.1`")
            st.markdown("**Audit mode** `offline / local`")
            st.caption("API keys are read from environment or Streamlit Secrets; this page never prints them.")
        with st.container(border=True):
            section("Audit counters", "Static audit artifacts, not live counters.")
            st.dataframe([
                {"class": "A · implemented", "count": counts.get("A", "N/A")},
                {"class": "B · design-only", "count": counts.get("B", "N/A")},
                {"class": "C · concept/external", "count": counts.get("C", "N/A")},
            ], hide_index=True, width="stretch", alt="A/B/C audit counts")
            source_note("patent_audit/counts.json")
    with right:
        with st.container(border=True):
            section("Database tables", "Read-only counts from SQLite.")
            tables = db.get("tables") or {}
            if tables:
                st.dataframe([{"table": k, "rows": v} for k, v in tables.items()],
                             hide_index=True, width="stretch", alt="Database table row counts")
            else:
                st.caption("Database unavailable.")
        with st.container(border=True):
            section("Data export")
            latest = latest_full_summary()
            if latest:
                st.caption(f"latest run: {latest.get('run_id')}")
                st.download_button(
                    "Download latest run report",
                    data=json.dumps(latest, ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name=f"{latest.get('run_id', 'run')}.json",
                    mime="application/json",
                    icon=":material/download:",
                )
            else:
                st.caption("No saved run available for export.")
            st.caption("Raw SQLite is read-only in the app; no database write is provided here.")
        with st.container(border=True):
            section("About")
            st.markdown("**BOPET Intelligence**")
            st.caption("Evidence-Constrained Industrial Optimization Platform")
            st.caption("Research prototype. Production and economic values are scenario estimates; "
                       "no field data or PLC/MES connection is claimed.")
    if legacy_database is not None:
        with st.expander("Original database and deployment view", expanded=False):
            legacy_database()
    source_note("config.py · .streamlit/config.toml · patent_audit")
