# -*- coding: utf-8 -*-
"""Atomic run checkpoints (records + archive + state)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.archive import AntiRegressionArchive


class CheckpointError(RuntimeError):
    pass


class CheckpointManager:
    @staticmethod
    def save(path: str | Path, *, run_id: str, records: list[dict[str, Any]],
             archive: AntiRegressionArchive, state: dict[str, Any],
             extra: dict[str, Any] | None = None) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": run_id,
            "records": records,
            "archive": archive.to_dict(),
            "state": state,
            "extra": extra or {},
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @staticmethod
    def load(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            raise CheckpointError(f"checkpoint not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("run_id", "records", "archive", "state"):
            if key not in data:
                raise CheckpointError(f"checkpoint missing {key}")
        return data
