# -*- coding: utf-8 -*-
"""Design tokens and small native UI helpers for BOPET Intelligence."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
COLORS = {
    "bg": "#F7F8FA",
    "surface": "#FFFFFF",
    "ink": "#172033",
    "muted": "#64748B",
    "brand": "#2455A4",
    "blue": "#3974CA",
    "border": "#E2E8F0",
    "success": "#16835B",
    "warning": "#D97706",
    "danger": "#DC2626",
}


def inject_styles() -> None:
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")


def page_header(title: str, subtitle: str = "", kicker: str = "") -> None:
    if kicker:
        st.markdown(f'<div class="bi-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def section(title: str, description: str = "") -> None:
    st.subheader(title)
    if description:
        st.caption(description)


def source_note(text: str) -> None:
    st.caption(f"Source: {text}")


def empty_state(title: str, body: str, icon: str = ":material/info:") -> None:
    with st.container(border=True):
        st.markdown(f"**{icon} {title}**")
        st.caption(body)


def fmt(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:,.{digits}f}%"
    except (TypeError, ValueError):
        return "N/A"


def badge(text: str, tone: str = "gray") -> None:
    st.markdown(f":{tone}-badge[{text}]")
