# -*- coding: utf-8 -*-
"""Read-only typed evidence catalog over the existing SQLite database.

The raw DB is preserved. Rows are mapped to EvidenceRecord without changing
the original tables; verification status stays UNVERIFIED until human review.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.schemas import EvidenceRecord

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "database" / "bopet.db"
TABLES = ("evidence_01_50", "evidence_51_100")


def _connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"evidence database not found: {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load_records(*, db_path: str | Path = DEFAULT_DB, limit: int | None = None,
                 table: str = "evidence_01_50") -> list[EvidenceRecord]:
    if table not in TABLES:
        raise ValueError(f"unsupported table: {table}")
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = f"select * from {table}"  # table is allow-listed above
        if limit is not None:
            sql += f" limit {int(limit)}"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()

    out: list[EvidenceRecord] = []
    for idx, row in enumerate(rows):
        data = dict(row)
        title = str(data.get("题名", ""))
        paper_id = str(data.get("编号", ""))
        page = data.get("页码")
        text = str(data.get("原页量化证据（截断）", ""))
        out.append(EvidenceRecord(
            evidence_id=f"{table}-{paper_id}-{page}-{idx}",
            source_id=paper_id,
            title=title,
            source_page=int(page) if page is not None else None,
            source_text=text,
            source_table=table,
            parameter_name=str(data.get("数据类型", "")),
            evidence_grade="UNVERIFIED",
            verification_status="UNVERIFIED",
            applicability_conditions={
                "material": "待核实",
                "equipment": "待核实",
                "source_pdf": str(data.get("本地PDF", "")),
                "topic": str(data.get("主题分类", "")),
                "relevance_score": data.get("相关性评分"),
            },
        ))
    return out


def catalog_stats(*, db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        counts = {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in TABLES}
        papers = conn.execute(
            "select count(distinct 编号) from (select 编号 from evidence_01_50 union all select 编号 from evidence_51_100)"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "tables": counts,
        "total_evidence_rows": sum(counts.values()),
        "distinct_papers": papers,
        "verification": "UNVERIFIED; raw rows are not production constraints",
    }
