# -*- coding: utf-8 -*-
"""受控写入演示适配器。

这不是 PLC/OPC UA 驱动。它只把 setpoint 写入本地 JSON 审计日志，
用于演示“预演 → 校验 → 审批 → 写入 → 回滚”的完整闭环。

真实产线接入必须替换本模块的 write/rollback 实现，并完成：
- OPC UA / PLC 标签映射与限幅、限速；
- 安全联锁与急停回路评审；
- 现场标定、FAT/SAT 与变更审批。
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "control"
LOG_PATH = DATA_DIR / "control_log.json"
LOCK = threading.Lock()

MODE = "DEMO"
MODE_LABEL = "本地演示（不连接真实 PLC）"

# 只演示 5 个可写变量；其余 19 项仍是只读/待标定。
PARAMETERS: dict[str, dict[str, Any]] = {
    "lip_gap_mm": {
        "label": "模唇间隙",
        "unit": "mm",
        "min": 0.0,
        "max": 1.0,
        "step": 0.01,
        "baseline": 0.35,
        "max_delta": 0.02,
        "evidence": "1-03 / 1-06",
    },
    "choker_pct": {
        "label": "Choker 开度",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "step": 1.0,
        "baseline": 48.0,
        "max_delta": 5.0,
        "evidence": "1-03",
    },
    "drum_temp_c": {
        "label": "冷鼓温度",
        "unit": "°C",
        "min": 15.0,
        "max": 35.0,
        "step": 0.5,
        "baseline": 22.0,
        "max_delta": 2.0,
        "evidence": "1-12",
    },
    "speed_trim_pct": {
        "label": "线速度调整",
        "unit": "%",
        "min": -10.0,
        "max": 15.0,
        "step": 0.5,
        "baseline": 0.0,
        "max_delta": 15.0,
        "evidence": "2-03 / 2-08",
    },
    "taper_pct": {
        "label": "收卷 taper",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "step": 1.0,
        "baseline": 35.0,
        "max_delta": 10.0,
        "evidence": "3-10",
    },
}

# 只读、用于演示“材料边界仍在校验”的固定值。
FIXED_MATERIAL = {
    "IV_dL_g": 0.64,
    "IPA_mol_pct": 0.0,
    "rPET_wt_pct": 12.0,
    "DBS_wt_pct": 0.60,
}

INITIAL_STATE = {
    "lip_gap_mm": 0.35,
    "choker_pct": 48.0,
    "drum_temp_c": 22.0,
    "speed_trim_pct": 0.0,
    "taper_pct": 35.0,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_store() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not LOG_PATH.exists():
            _save({"state": deepcopy(INITIAL_STATE), "log": []})
    except OSError:
        # 云端只读文件系统：允许应用启动，写入时再由 UI 报错。
        return


def _load() -> dict[str, Any]:
    _ensure_store()
    try:
        raw = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    state = deepcopy(INITIAL_STATE)
    state.update(raw.get("state") or {})
    log = raw.get("log") or []
    return {"state": state, "log": log}


def _save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, LOG_PATH)


def get_state() -> dict[str, float]:
    with LOCK:
        return deepcopy(_load()["state"])


def get_log(limit: int = 20) -> list[dict[str, Any]]:
    with LOCK:
        log = _load()["log"]
    return list(reversed(log))[:limit]


def compute_dr(setpoints: dict[str, float]) -> float:
    """演示近似：线速度调整 1% → DR 约 +1%。

    只用来说明“提速会触发 DR 预检”，不是产线换算公式。
    """

    return 18.4 * (1.0 + float(setpoints.get("speed_trim_pct", 0.0)) / 100.0)


def _as_number(value: Any) -> float:
    return round(float(value), 4)


def validate(
    candidate: dict[str, float],
    current: dict[str, float] | None = None,
) -> list[dict[str, str]]:
    """返回逐项检查结果：ok / warn / block。"""

    current = current or get_state()
    checks: list[dict[str, str]] = []

    for key, meta in PARAMETERS.items():
        value = float(candidate.get(key, meta["baseline"]))
        if value < meta["min"] or value > meta["max"]:
            checks.append(
                {
                    "项目": meta["label"],
                    "建议值": f"{value:g} {meta['unit']}",
                    "状态": "block",
                    "说明": f"超出范围 {meta['min']:g}—{meta['max']:g} {meta['unit']}",
                    "证据": meta["evidence"],
                }
            )
            continue

        delta = value - float(current.get(key, meta["baseline"]))
        if abs(delta) > meta["max_delta"] and key != "speed_trim_pct":
            checks.append(
                {
                    "项目": meta["label"],
                    "建议值": f"{value:g} {meta['unit']}",
                    "状态": "block",
                    "说明": (
                        f"单次变化 {delta:+g} {meta['unit']}，"
                        f"超过演示步长 ±{meta['max_delta']:g} {meta['unit']}"
                    ),
                    "证据": meta["evidence"],
                }
            )
        elif abs(delta) > 0:
            checks.append(
                {
                    "项目": meta["label"],
                    "建议值": f"{value:g} {meta['unit']}",
                    "状态": "ok",
                    "说明": f"变化 {delta:+g} {meta['unit']}，在演示步长内",
                    "证据": meta["evidence"],
                }
            )
        else:
            checks.append(
                {
                    "项目": meta["label"],
                    "建议值": f"{value:g} {meta['unit']}",
                    "状态": "ok",
                    "说明": "未调整",
                    "证据": meta["evidence"],
                }
            )

    dr = compute_dr(candidate)
    if dr > 20.3:
        checks.append(
            {
                "项目": "铸片拉伸比 DR",
                "建议值": f"{dr:.2f}",
                "状态": "block",
                "说明": "DR > 20.3：B 级文献阈值，预检拒绝；不是本厂联锁",
                "证据": "2-03",
            }
        )
    elif dr > 19.8:
        checks.append(
            {
                "项目": "铸片拉伸比 DR",
                "建议值": f"{dr:.2f}",
                "状态": "warn",
                "说明": "DR 接近 20.3，建议先降速或降温再试",
                "证据": "2-03",
            }
        )
    else:
        checks.append(
            {
                "项目": "铸片拉伸比 DR",
                "建议值": f"{dr:.2f}",
                "状态": "ok",
                "说明": "低于 20.3；本厂仍需标定",
                "证据": "2-03",
            }
        )

    material_checks = [
        ("IV", FIXED_MATERIAL["IV_dL_g"], 0.5, 0.9, "dL/g", "4-01"),
        ("IPA", FIXED_MATERIAL["IPA_mol_pct"], 0.0, 20.0, "mol%", "4-02"),
        ("rPET", FIXED_MATERIAL["rPET_wt_pct"], 0.0, 30.0, "wt%", "4-11"),
        ("DBS", FIXED_MATERIAL["DBS_wt_pct"], 0.5, 0.7, "wt%", "4-06"),
    ]
    for name, value, low, high, unit, evidence in material_checks:
        checks.append(
            {
                "项目": name,
                "建议值": f"{value:g} {unit}",
                "状态": "ok" if low <= value <= high else "block",
                "说明": f"只读材料边界 {low:g}—{high:g} {unit}",
                "证据": evidence,
            }
        )

    return checks


def has_blocker(checks: list[dict[str, str]]) -> bool:
    return any(item["状态"] == "block" for item in checks)


def preview(
    candidate: dict[str, float],
    current: dict[str, float] | None = None,
) -> dict[str, Any]:
    """简化工程预演，不是数字孪生；用于演示“先预演、再审批”。"""

    current = current or get_state()
    d_lip = float(candidate["lip_gap_mm"]) - float(current["lip_gap_mm"])
    d_choker = float(candidate["choker_pct"]) - float(current["choker_pct"])
    d_temp = float(candidate["drum_temp_c"]) - float(current["drum_temp_c"])
    d_speed = float(candidate["speed_trim_pct"]) - float(current["speed_trim_pct"])
    d_taper = float(candidate["taper_pct"]) - float(current["taper_pct"])
    dr = compute_dr(candidate)

    sigma = (
        2.40
        + 6.0 * abs(d_lip)
        + 0.004 * abs(d_choker)
        + 0.030 * abs(d_temp)
        + 0.020 * abs(d_speed)
        + 0.002 * abs(d_taper)
    )
    if dr > 20.3:
        sigma += 1.20

    trim = 5.00 + 4.0 * abs(d_lip) + 0.010 * abs(d_temp) + 0.008 * abs(d_speed)
    downgrade = 5.20 + 5.0 * abs(d_lip) + 0.020 * abs(d_temp) + 0.012 * abs(d_speed)
    qualified = 530.0 * (
        1.0
        - max(0.0, trim - 5.0) / 100.0
        - max(0.0, downgrade - 5.2) / 100.0
    )

    if sigma >= 2.8 or dr > 20.3:
        risk = "高"
    elif sigma >= 2.6 or dr > 19.8:
        risk = "中"
    else:
        risk = "低"

    return {
        "thickness_sigma_um": round(sigma, 2),
        "trim_rate_pct": round(trim, 2),
        "downgrade_rate_pct": round(downgrade, 2),
        "qualified_t": round(qualified, 1),
        "dr": round(dr, 2),
        "risk": risk,
        "mode": "SIMPLIFIED_ENGINEERING_MODEL",
        "note": "简化工程预演，不是数字孪生，也不是产线实测。",
    }


def _next_id(log: list[dict[str, Any]], prefix: str) -> str:
    date = datetime.now().strftime("%Y%m%d")
    count = sum(1 for item in log if item.get("id", "").startswith(f"{prefix}-{date}")) + 1
    return f"{prefix}-{date}-{count:03d}"


def write_setpoints(
    candidate: dict[str, float],
    approver: str,
    note: str = "",
) -> dict[str, Any]:
    """审批后写入本地日志；任何 block 都会拒绝。"""

    approver = approver.strip()
    if not approver:
        raise ValueError("必须填写审批人。")

    with LOCK:
        data = _load()
        current = data["state"]
        checks = validate(candidate, current)
        if has_blocker(checks):
            raise ValueError("存在硬拦截项，不能写入。请先修正参数。")

        normalized = {
            key: _as_number(candidate.get(key, current.get(key, meta["baseline"])))
            for key, meta in PARAMETERS.items()
        }
        if all(abs(normalized[key] - current[key]) < 1e-9 for key in normalized):
            raise ValueError("当前参数没有变化，不需要写入。")

        record_id = _next_id(data["log"], "WR")
        record = {
            "id": record_id,
            "action": "write",
            "timestamp": _now(),
            "mode": MODE,
            "approver": approver,
            "note": note.strip(),
            "before": deepcopy(current),
            "after": normalized,
            "checks": checks,
            "preview": preview(normalized, current),
        }
        data["state"] = normalized
        data["log"].append(record)
        _save(data)
        return deepcopy(record)


def rollback(record_id: str, approver: str, note: str = "") -> dict[str, Any]:
    """回滚到指定 write 记录之前的 setpoint。"""

    approver = approver.strip()
    if not approver:
        raise ValueError("必须填写回滚审批人。")

    with LOCK:
        data = _load()
        target = next(
            (
                item
                for item in data["log"]
                if item.get("id") == record_id and item.get("action") == "write"
            ),
            None,
        )
        if target is None:
            raise ValueError(f"找不到写入记录：{record_id}")

        before = deepcopy(target["before"])
        record = {
            "id": _next_id(data["log"], "RB"),
            "action": "rollback",
            "timestamp": _now(),
            "mode": MODE,
            "approver": approver,
            "note": note.strip() or f"回滚 {record_id}",
            "target": record_id,
            "before": deepcopy(data["state"]),
            "after": before,
            "checks": [],
            "preview": preview(before, data["state"]),
        }
        data["state"] = before
        data["log"].append(record)
        _save(data)
        return deepcopy(record)


def log_rows(limit: int = 20) -> list[dict[str, Any]]:
    """把嵌套日志摊平成可直接展示的行。"""

    rows: list[dict[str, Any]] = []
    for item in get_log(limit):
        after = item.get("after") or {}
        rows.append(
            {
                "记录": item.get("id", ""),
                "时间": item.get("timestamp", ""),
                "动作": "写入" if item.get("action") == "write" else "回滚",
                "审批人": item.get("approver", ""),
                "模唇/mm": after.get("lip_gap_mm", ""),
                "冷鼓/°C": after.get("drum_temp_c", ""),
                "线速/%": after.get("speed_trim_pct", ""),
                "taper/%": after.get("taper_pct", ""),
                "模式": item.get("mode", ""),
            }
        )
    return rows
