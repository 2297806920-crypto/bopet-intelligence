# -*- coding: utf-8 -*-
"""Unified sidebar navigation and product chrome."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui.data import api_label, api_name, db_snapshot

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    ("overview", "01  系统总览", ":material/space_dashboard:"),
    ("evidence", "02  证据知识库", ":material/database:"),
    ("constraints", "03  数理约束", ":material/rule:"),
    ("optimization", "04  智能优化", ":material/tune:"),
    ("evaluation", "05  多维评价", ":material/analytics:"),
    ("validation", "06  实验验证", ":material/science:"),
    ("review", "07  工程审核", ":material/fact_check:"),
    ("settings", "08  系统设置", ":material/settings:"),
]


def render_sidebar() -> tuple[str, bool]:
    with st.sidebar:
        st.logo(str(ROOT / "assets" / "logo.svg"), size="large")
        st.markdown("**BOPET Intelligence**")
        st.caption("Evidence-Constrained Industrial Optimization")
        st.caption("V3.0  ·  research workspace")

        labels = [label for _, label, _ in PAGES]
        page_label = st.radio(
            "Workspace",
            labels,
            key="nav",
            label_visibility="collapsed",
        )
        page = next(key for key, label, _ in PAGES if label == page_label)

        st.caption("SYSTEM")
        demo = st.toggle(
            "演示模式",
            key="demo_mode",
            help="回放最近一次真实保存的运行结果；不是虚构实验数据。",
        )
        if demo:
            st.markdown(":blue-badge[DEMO · 历史回放]")

        st.divider()
        db = db_snapshot()
        if db.get("exists") and db.get("tables"):
            st.markdown(":green-badge[Database] connected")
        else:
            st.markdown(":red-badge[Database] unavailable")
        api_text, api_tone = api_label()
        st.markdown(f":{api_tone}-badge[API] {api_text}")
        st.caption(f"provider · {api_name()}")

        st.divider()
        st.caption("文献库为只读证据；生产数字为工程估算。")
        st.caption("不连接 PLC/MES。")
    return page, demo
