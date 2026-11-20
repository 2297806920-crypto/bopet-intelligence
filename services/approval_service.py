# -*- coding: utf-8 -*-
"""Engineer approval records; no LLM can approve or write to a PLC."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.schemas import CandidatePlan, EvaluationResult


class ApprovalError(RuntimeError):
    pass


class ApprovalService:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def submit(self, candidate: CandidatePlan, evaluation: EvaluationResult,
               reviewer: str, decision: str, note: str = "") -> dict[str, Any]:
        if decision not in ("APPROVED", "REJECTED", "NEEDS_DATA"):
            raise ApprovalError("decision must be APPROVED, REJECTED or NEEDS_DATA")
        if decision == "APPROVED" and not evaluation.hard_feasible:
            raise ApprovalError("cannot approve a hard-infeasible candidate")
        if decision == "APPROVED" and evaluation.missing_fields:
            raise ApprovalError("cannot approve with missing required fields")
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "reviewer": reviewer,
            "decision": decision,
            "note": note,
            "candidate": candidate.model_dump(mode="json"),
            "evaluation_version": evaluation.evaluation_version,
            "hard_feasible": evaluation.hard_feasible,
            "missing_fields": evaluation.missing_fields,
            "data_mode": evaluation.data_mode.value if hasattr(evaluation.data_mode, "value") else str(evaluation.data_mode),
            "llm_approved": False,
            "plant_write": False,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def latest(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        lines = [l for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else None
