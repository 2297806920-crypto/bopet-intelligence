# -*- coding: utf-8 -*-
"""Cached readers over the real project data and artifacts."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "database" / "bopet.db"
OUTPUTS = ROOT / "outputs"


@st.cache_data(ttl=60, show_spinner=False)
def db_snapshot() -> dict[str, Any]:
    if not DB_PATH.exists():
        return {"exists": False, "path": str(DB_PATH), "tables": {}}
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        tables = {}
        for (name,) in conn.execute("select name from sqlite_master where type='table' order by name"):
            try:
                tables[name] = conn.execute(f'select count(*) from "{name}"').fetchone()[0]
            except sqlite3.DatabaseError:
                tables[name] = None
    finally:
        conn.close()
    return {"exists": True, "path": str(DB_PATH), "tables": tables}


@st.cache_data(ttl=60, show_spinner=False)
def evidence_rows(limit: int = 4000) -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows: list[dict[str, Any]] = []
    try:
        for table in ("evidence_01_50", "evidence_51_100"):
            sql = f'select * from "{table}" limit {int(limit)}'  # allow-listed literal
            for row in conn.execute(sql):
                d = dict(row)
                rows.append({
                    "table": table,
                    "paper": d.get("编号"),
                    "topic": d.get("主题分类"),
                    "title": d.get("题名"),
                    "page": d.get("页码"),
                    "parameter_type": d.get("数据类型"),
                    "relevance": d.get("相关性评分"),
                    "text": d.get("原页量化证据（截断）"),
                    "pdf": d.get("本地PDF"),
                    "verification": "UNVERIFIED",
                })
    finally:
        conn.close()
    return rows


@st.cache_data(ttl=30, show_spinner=False)
def latest_run() -> dict[str, Any] | None:
    candidates = sorted(
        (p for p in (OUTPUTS / "v3_runs").glob("*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        best = data.get("best_evaluation") or {}
        return {
            "run_id": data.get("run_id"),
            "scenario": data.get("scenario"),
            "seed": data.get("seed"),
            "iterations": data.get("iterations"),
            "evaluations": data.get("candidates_evaluated"),
            "stop_reason": data.get("stop_reason"),
            "best_objective": best.get("objective_value"),
            "data_mode": data.get("data_mode"),
            "elapsed_s": data.get("elapsed_s"),
            "path": str(path.parent),
            "modified": path.stat().st_mtime,
        }
    return None


@st.cache_data(ttl=30, show_spinner=False)
def latest_full_summary() -> dict[str, Any] | None:
    candidates = sorted(
        (p for p in (OUTPUTS / "v3_runs").glob("*/summary.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


@st.cache_data(ttl=60, show_spinner=False)
def experiment_summary() -> dict[str, Any] | None:
    for path in (
        OUTPUTS / "v31_experiments" / "optimizer_comparison_summary.json",
        OUTPUTS / "v3_experiments" / "optimizer_comparison_summary.json",
    ):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return None


@st.cache_data(show_spinner=False)
def test_count() -> str:
    for path in (
        ROOT / "patent_audit" / "test_count.txt",
        ROOT / "copyright_materials" / "tests" / "pytest_count.txt",
    ):
        if path.exists():
            text = path.read_text(encoding="utf-8-sig").strip()
            if "collected" in text:
                return text.splitlines()[0]
    return "未找到测试记录"


@st.cache_data(show_spinner=False)
def audit_counts() -> dict[str, int] | None:
    path = ROOT / "patent_audit" / "counts.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return {
            "A": data.get("A_implemented"),
            "B": data.get("B_design_only"),
            "C": data.get("C_concept_only"),
        }
    except (OSError, json.JSONDecodeError):
        return None


def api_label() -> tuple[str, str]:
    key = os.getenv("INTERNLM_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
    model = os.getenv("LLM_MODEL") or os.getenv("INTERNLM_MODEL")
    if key and model:
        return "API configured", "green"
    return "API not configured", "orange"


def api_name() -> str:
    return os.getenv("LLM_PROVIDER", "internlm")
