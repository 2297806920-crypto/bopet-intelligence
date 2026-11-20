# -*- coding: utf-8 -*-
"""Reusable native components shared by BOPET Intelligence pages."""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

from ui.theme import COLORS, source_note


def kpi_row(items: Iterable[dict]) -> None:
    items = list(items)
    with st.container(horizontal=True, gap="small"):
        for item in items:
            st.metric(
                item["label"],
                item["value"],
                item.get("delta"),
                delta_description=item.get("delta_description"),
                border=True,
                help=item.get("help"),
            )


def status_line(label: str, value: str, tone: str = "gray") -> None:
    st.markdown(f":{tone}-badge[{html.escape(label)}] **{html.escape(value)}**")


def flow(items: list[tuple[str, str]]) -> None:
    """Static architecture chain; labels are code-owned, not DB/LLM text."""
    pieces = []
    for index, (label, caption) in enumerate(items):
        pieces.append(
            f'<span title="{html.escape(caption)}">{html.escape(label)}</span>'
        )
        if index != len(items) - 1:
            pieces.append('<span style="border:0;background:transparent;color:#94A3B8">→</span>')
    st.markdown(f'<div class="bi-flow">{"".join(pieces)}</div>', unsafe_allow_html=True)


def comparison_table(rows: list[dict], *, empty: str = "暂无数据") -> None:
    if not rows:
        st.caption(empty)
        return
    st.dataframe(rows, hide_index=True, width="stretch",
                 alt="Comparison table with measured values")


def data_note(text: str) -> None:
    source_note(text)
