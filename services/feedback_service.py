# -*- coding: utf-8 -*-
"""Trial feedback import. Simulated rows must be labeled SIMULATED."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

TEMPLATE_COLUMNS = [
    "trial_id", "timestamp", "candidate_id", "product", "thickness_um",
    "line_speed_m_min", "stretch_temp_c", "td_ratio", "quality_yield",
    "downtime_h", "transition_h", "unit_cost", "data_mode", "notes",
]


class FeedbackError(ValueError):
    pass


class FeedbackService:
    def __init__(self, data_dir: str | Path = "data/feedback"):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def write_template(self) -> Path:
        path = self.dir / "trial_feedback_template.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(TEMPLATE_COLUMNS)
            writer.writerow([
                "T-EXAMPLE", "2026-11-20T10:00:00", "candidate-001", "C 电气绝缘薄膜",
                "100", "80", "95", "3.2", "0.875", "33", "37", "8128",
                "SIMULATED", "replace with real trial data; SIMULATED is not field data",
            ])
        return path

    def import_csv(self, path: str | Path, *, require_field_data: bool = False) -> list[dict[str, Any]]:
        path = Path(path)
        if not path.exists():
            raise FeedbackError(f"file not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            raise FeedbackError("empty CSV")
        missing = [c for c in TEMPLATE_COLUMNS if c not in rows[0]]
        if missing:
            raise FeedbackError(f"missing columns: {missing}")
        if require_field_data and any(r.get("data_mode") != "FIELD_DATA" for r in rows):
            raise FeedbackError("require_field_data=True but a row is not FIELD_DATA")
        out = []
        for row in rows:
            out.append({
                "imported_at": datetime.now().isoformat(timespec="seconds"),
                "data_mode": row.get("data_mode", "UNKNOWN"),
                "source_file": path.name,
                "row": row,
            })
        self._append(out)
        return out

    def _append(self, rows: list[dict[str, Any]]) -> None:
        path = self.dir / "trial_feedback.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
