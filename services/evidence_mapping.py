# -*- coding: utf-8 -*-
"""Evidence-to-constraint mapping.

This is a draft/registry layer. Literature extraction never becomes a plant
hard interlock automatically: every link carries verification and calibration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.schemas import DecisionVariable


class MappingError(ValueError):
    pass


def load_mapping(path: str | Path = "data/constraints/bopet_v3.json") -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != "v3.0":
        raise MappingError("unsupported constraint map version")
    for row in data.get("variables", []):
        if not row.get("evidence_ids"):
            raise MappingError(f"{row.get('variable_id')} has no evidence ids")
        if row.get("lower_bound") is None or row.get("upper_bound") is None:
            raise MappingError(f"{row.get('variable_id')} has no bounds")
    return data


def to_variables(data: dict[str, Any]) -> list[DecisionVariable]:
    return [DecisionVariable.model_validate(row) for row in data["variables"]]


def mapping_table(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "variable_id": row["variable_id"],
        "name": row["name"],
        "constraint_type": row["constraint_type"],
        "lower": row["lower_bound"],
        "upper": row["upper_bound"],
        "unit": row["unit"],
        "calibration_status": row["calibration_status"],
        "evidence_ids": ", ".join(row["evidence_ids"]),
        "verification": "draft/offline; field calibration required",
    } for row in data["variables"]]
