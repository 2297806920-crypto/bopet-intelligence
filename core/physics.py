# -*- coding: utf-8 -*-
"""F01-F07 physics relationships.

All inputs use SI units unless a function explicitly says otherwise.
The module contains deterministic calculations only; no ML or plant claim.
"""

from __future__ import annotations

import math
from typing import Any


class PhysicsError(ValueError):
    """Invalid physical input."""


class MissingDataError(PhysicsError):
    """Required physical context is missing; result must be UNKNOWN."""


def _positive(name: str, value: float | None) -> float:
    if value is None:
        raise MissingDataError(f"{name} is required")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise PhysicsError(f"{name} must be a finite positive number, got {value!r}")
    return value


def mass_flow(density_kg_m3: float, width_m: float, thickness_m: float,
              speed_m_s: float) -> float:
    """F01: m_dot = rho * b * h * v, kg/s."""
    rho = _positive("density_kg_m3", density_kg_m3)
    b = _positive("width_m", width_m)
    h = _positive("thickness_m", thickness_m)
    v = _positive("speed_m_s", speed_m_s)
    return rho * b * h * v


def solve_thickness_from_mass(m_dot_kg_s: float, density_kg_m3: float,
                              width_m: float, speed_m_s: float) -> float:
    """F01 inverse: h = m_dot / (rho * b * v), m."""
    m_dot = _positive("m_dot_kg_s", m_dot_kg_s)
    rho = _positive("density_kg_m3", density_kg_m3)
    b = _positive("width_m", width_m)
    v = _positive("speed_m_s", speed_m_s)
    return m_dot / (rho * b * v)


def md_stretch_ratio(v_out_m_s: float, v_in_m_s: float) -> float:
    """F02: lambda_MD = v_out / v_in. This is NOT draw ratio DR."""
    return _positive("v_out_m_s", v_out_m_s) / _positive("v_in_m_s", v_in_m_s)


def td_stretch_ratio(width_out_m: float, width_in_m: float) -> float:
    """F03: lambda_TD = b_out / b_in."""
    return _positive("width_out_m", width_out_m) / _positive("width_in_m", width_in_m)


def average_final_thickness(h_cast_m: float, rho_cast_kg_m3: float,
                            rho_final_kg_m3: float,
                            lambda_md: float, lambda_td: float) -> float:
    """F04: average thickness after biaxial stretching.

    h_final = h_cast * (rho_cast / rho_final) / (lambda_MD * lambda_TD)

    This is an average estimate, not a full CD thickness profile model.
    """
    h_cast = _positive("h_cast_m", h_cast_m)
    rho_cast = _positive("rho_cast_kg_m3", rho_cast_kg_m3)
    rho_final = _positive("rho_final_kg_m3", rho_final_kg_m3)
    lm = _positive("lambda_md", lambda_md)
    lt = _positive("lambda_td", lambda_td)
    return h_cast * (rho_cast / rho_final) / (lm * lt)


def mass_balance_residual(m_in_kg_s: float, m_out_kg_s: float,
                          epsilon: float = 1e-12) -> float:
    """F05: normalized mass balance residual."""
    if not math.isfinite(float(m_in_kg_s)) or not math.isfinite(float(m_out_kg_s)):
        raise PhysicsError("mass flows must be finite")
    if float(m_in_kg_s) < 0 or float(m_out_kg_s) < 0:
        raise PhysicsError("mass flows must be non-negative")
    eps = _positive("epsilon", epsilon)
    return abs(float(m_in_kg_s) - float(m_out_kg_s)) / max(abs(float(m_in_kg_s)), eps)


def engineering_strain(length_m: float, initial_length_m: float) -> float:
    """F06: engineering strain = (L - L0) / L0."""
    l0 = _positive("initial_length_m", initial_length_m)
    l = _positive("length_m", length_m)
    return (l - l0) / l0


def true_strain(length_m: float, initial_length_m: float) -> float:
    """F06: true strain = ln(L / L0)."""
    l0 = _positive("initial_length_m", initial_length_m)
    l = _positive("length_m", length_m)
    return math.log(l / l0)


def strain_rate_from_speed(v_in_m_s: float, v_out_m_s: float,
                           zone_length_m: float) -> float:
    """F06 simplification: (v_out - v_in) / zone_length, 1/s.

    This is only valid when a finite stretching zone length is supplied.
    """
    v_in = _positive("v_in_m_s", v_in_m_s)
    v_out = _positive("v_out_m_s", v_out_m_s)
    length = _positive("zone_length_m", zone_length_m)
    return (v_out - v_in) / length


def strain_rate(duration_s: float | None, true_strain_value: float | None) -> float:
    """F06: true strain / duration. Missing duration => UNKNOWN, not zero."""
    duration = _positive("duration_s", duration_s)
    if true_strain_value is None:
        raise MissingDataError("true_strain_value is required")
    return float(true_strain_value) / duration


def strength_safety_margin(allowable_strength_mpa: float | None,
                           actual_stress_mpa: float | None) -> float:
    """F07: M = sigma_allowable / sigma_actual.

    Raises MissingDataError if either side is unavailable. Do not invent a
    material allowable stress or a plant stress value.
    """
    allowable = _positive("allowable_strength_mpa", allowable_strength_mpa)
    actual = _positive("actual_stress_mpa", actual_stress_mpa)
    return allowable / actual


def safe_strength_margin(allowable_strength_mpa: float | None,
                         actual_stress_mpa: float | None) -> dict[str, Any]:
    """F07 UI/engine-safe wrapper: returns UNKNOWN instead of a fake margin."""
    if allowable_strength_mpa is None or actual_stress_mpa is None:
        return {
            "status": "UNKNOWN",
            "margin": None,
            "reason": "allowable strength or actual stress is missing",
        }
    try:
        return {
            "status": "PASS",
            "margin": strength_safety_margin(allowable_strength_mpa, actual_stress_mpa),
            "reason": "",
        }
    except PhysicsError as exc:
        return {"status": "UNKNOWN", "margin": None, "reason": str(exc)}


FORMULAS = {
    "F01": {
        "name": "质量守恒",
        "expression": "m_dot = rho * b * h * v",
        "implemented": True,
        "source": "continuity; SI units",
        "tested": "tests/test_physics.py",
    },
    "F02": {
        "name": "纵向拉伸倍率",
        "expression": "lambda_MD = v_out / v_in",
        "implemented": True,
        "source": "kinematics; not DR",
        "tested": "tests/test_physics.py",
    },
    "F03": {
        "name": "横向拉伸倍率",
        "expression": "lambda_TD = b_out / b_in",
        "implemented": True,
        "source": "kinematics",
        "tested": "tests/test_physics.py",
    },
    "F04": {
        "name": "双拉平均厚度",
        "expression": "h_final = h_cast*(rho_cast/rho_final)/(lambda_MD*lambda_TD)",
        "implemented": True,
        "source": "mass conservation; average estimate only",
        "tested": "tests/test_physics.py",
    },
    "F05": {
        "name": "质量守恒残差",
        "expression": "abs(m_in-m_out)/max(abs(m_in), eps)",
        "implemented": True,
        "source": "normalized residual; tolerance configurable",
        "tested": "tests/test_physics.py",
    },
    "F06": {
        "name": "应变与应变速率",
        "expression": "engineering=(L-L0)/L0; true=ln(L/L0); rate=true/time",
        "implemented": True,
        "source": "kinematics; missing duration => UNKNOWN",
        "tested": "tests/test_physics.py",
    },
    "F07": {
        "name": "强度安全裕度",
        "expression": "M = sigma_allowable / sigma_actual",
        "implemented": True,
        "source": "requires valid material allowable and stress",
        "tested": "tests/test_physics.py",
    },
}
