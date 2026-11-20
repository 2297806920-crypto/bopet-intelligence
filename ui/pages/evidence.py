# -*- coding: utf-8 -*-
"""Evidence knowledge base: compact search, filters and details."""

from __future__ import annotations

from typing import Callable

import streamlit as st

from ui.components import kpi_row
from ui.data import evidence_rows
from ui.theme import page_header, section, source_note


def render(legacy_qa: Callable[[], None]) -> None:
    rows = evidence_rows()
    page_header(
        "Evidence knowledge base",
        "Search the read-only evidence archive; verification stays explicit.",
        kicker="WORKSPACE 02 · EVIDENCE",
    )
    kpi_row([
        {"label": "Evidence rows loaded", "value": f"{len(rows):,}"},
        {"label": "Distinct papers", "value": f"{len({r['paper'] for r in rows}):,}"},
        {"label": "Verified records", "value": "0",
         "help": "The current archive has no human-verified evidence records."},
        {"label": "Material field", "value": "待核实",
         "help": "The source table has no structured material column; no material is inferred."},
    ])

    with st.container(border=True):
        section("Search and filters", "Filters apply to the loaded evidence rows only.")
        c1, c2 = st.columns([2, 1])
        with c1:
            query = st.text_input("Search title or evidence text", key="evidence_query",
                                  placeholder="拉伸温度 / shrinkage / tension")
        with c2:
            paper = st.text_input("Paper ID", key="evidence_paper", placeholder="例如 1")

        c3, c4, c5, c6 = st.columns(4, gap="small")
        topics = sorted({str(r["topic"]) for r in rows if r["topic"]})
        params = sorted({str(r["parameter_type"]) for r in rows if r["parameter_type"]})
        with c3:
            topic_filter = st.multiselect("Topic", topics, key="evidence_topics")
        with c4:
            param_filter = st.multiselect("Parameter type", params, key="evidence_params")
        with c5:
            material_filter = st.selectbox("Material", ["全部", "待核实"], key="evidence_material",
                                           help="No structured material field exists in the source table.")
        with c6:
            grade_filter = st.selectbox("Evidence grade", ["全部", "UNVERIFIED"], key="evidence_grade")

        q = query.strip().lower()
        filtered = []
        for r in rows:
            if q and q not in str(r["title"]).lower() and q not in str(r["text"]).lower():
                continue
            if paper.strip() and paper.strip() not in str(r["paper"]):
                continue
            if topic_filter and str(r["topic"]) not in topic_filter:
                continue
            if param_filter and str(r["parameter_type"]) not in param_filter:
                continue
            if grade_filter == "UNVERIFIED" and r["verification"] != "UNVERIFIED":
                continue
            filtered.append(r)

        st.caption(f"{len(filtered):,} matching rows · material status: 待核实 (not inferred)")

        visible = [{
            "Paper": r["paper"],
            "Page": r["page"],
            "Topic": r["topic"],
            "Parameter": r["parameter_type"],
            "Relevance": r["relevance"],
            "Grade": r["verification"],
            "Title": r["title"],
        } for r in filtered[:500]]
        event = st.dataframe(
            visible,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="evidence_table",
            alt="Evidence table with paper, page, topic, parameter type and verification status",
            column_config={
                "Title": st.column_config.TextColumn("Title", width="large"),
                "Relevance": st.column_config.NumberColumn("Relevance", format="%d"),
            },
        )
        selected_rows = getattr(getattr(event, "selection", None), "rows", []) or []
        if selected_rows:
            r = filtered[selected_rows[0]]
            st.divider()
            section("Evidence detail", "Original text is shown on demand.")
            st.markdown(f"**{r['title']}**")
            st.caption(f"paper {r['paper']} · page {r['page']} · table {r['table']}")
            st.markdown(f":orange-badge[UNVERIFIED] :gray-badge[material 待核实]")
            st.json({
                "parameter_type": r["parameter_type"],
                "topic": r["topic"],
                "relevance": r["relevance"],
                "source_pdf": r["pdf"],
                "applicability": {"material": "待核实", "equipment": "待核实"},
            }, expanded=False)
            with st.expander("Original evidence excerpt", expanded=False):
                st.write(r["text"] or "N/A")
        source_note("data/database/bopet.db · evidence_01_50 / evidence_51_100 · read-only mode")

    with st.expander("Natural-language question answering (existing business function)", expanded=False):
        st.caption("This preserves the original Qwen/retrieval workflow. Without an API key, use retrieval-only mode.")
        legacy_qa()
