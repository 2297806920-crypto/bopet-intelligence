# -*- coding: utf-8 -*-
"""BOPET 24-variable process scenario (physics pre-check, not plant prediction).

The objective here is a transparent engineering proxy:
- hard variable windows;
- F05 mass-balance consistency;
- F04 average thickness vs a configured thickness target;
- preferred-window compliance.

It is deliberately NOT a trained quality/energy model and must stay
``SCENARIO_ESTIMATION``. The M1-M7 measure model remains the production/economics
adapter.
"""

from __future__ import annotations

from typing import Any

from core.constraints import ConstraintEngine
from core.physics import average_final_thickness, mass_balance_residual, mass_flow, solve_thickness_from_mass
from core.schemas import CandidatePlan, DataMode, EvaluationResult
from scenarios.bopet import BOPET_BASELINE, BOPET_VARIABLES

# Scenario assumptions, explicitly configurable and not plant measurements.
DENSITY_CAST = 1350.0       # kg/m3
DENSITY_FINAL = 1400.0      # kg/m3
WIDTH_M = 1.3               # m, pilot-line width assumption
TARGET_THICKNESS_UM = 12.0  # target product thickness
MASS_TOLERANCE = 0.05       # 5% normalized residual


class BOPETProcessScenario:
    name = "bopet_process_24"
    data_mode = DataMode.SCENARIO_ESTIMATION
    description = "24-variable physics/constraint pre-check; no trained quality model"
    variable_bounds = {
        v.variable_id: (v.lower_bound, v.upper_bound)
        for v in BOPET_VARIABLES if v.adjustable
    }
    discrete = False

    def sample(self, rng, iteration: int, strategy: str = "random") -> CandidatePlan:
        params = {v: float(rng.uniform(lo, hi)) for v, (lo, hi) in self.variable_bounds.items()}
        return CandidatePlan(
            candidate_id=f"process-{iteration}-{rng.randrange(10**6):06d}",
            iteration=iteration,
            parameters=params,
            generation_strategy=strategy,
            data_mode=self.data_mode,
        )

    def initial_candidate(self) -> CandidatePlan:
        return CandidatePlan(
            candidate_id="process-baseline",
            iteration=0,
            parameters=dict(BOPET_BASELINE),
            generation_strategy="baseline",
            data_mode=self.data_mode,
        )

    def evaluate(self, candidate: CandidatePlan) -> EvaluationResult:
        # Fill missing adjustable values from the baseline for deterministic
        # evaluation; generated candidates normally contain all of them.
        params = dict(BOPET_BASELINE)
        params.update(candidate.parameters)
        filled = CandidatePlan(
            candidate_id=candidate.candidate_id,
            iteration=candidate.iteration,
            parameters=params,
            generation_strategy=candidate.generation_strategy,
            data_mode=self.data_mode,
        )
        report = ConstraintEngine(BOPET_VARIABLES).evaluate(filled)

        line_speed_m_s = float(params["V08"]) / 60.0
        throughput_kg_h = float(params["V07"])
        # Derive cast thickness from throughput (F01 inverse), then rebuild the
        # mass flow to expose a checkable residual. The lip gap remains a
        # separate hard window; it is not equated to cast thickness.
        calculated_mass = throughput_kg_h / 3600.0
        cast_thickness_m = solve_thickness_from_mass(calculated_mass, DENSITY_CAST, WIDTH_M, line_speed_m_s)
        residual = mass_balance_residual(calculated_mass, mass_flow(DENSITY_CAST, WIDTH_M, cast_thickness_m, line_speed_m_s))
        thickness_m = average_final_thickness(
            cast_thickness_m, DENSITY_CAST, DENSITY_FINAL,
            float(params["V09"]), float(params["V10"]),
        )
        thickness_um = thickness_m * 1e6
        thickness_error = abs(thickness_um - TARGET_THICKNESS_UM) / TARGET_THICKNESS_UM

        hard = bool(report["hard_feasible"]) and residual <= MASS_TOLERANCE
        quality_score = max(0.0, 1.0 - thickness_error)
        mass_score = max(0.0, 1.0 - residual / MASS_TOLERANCE)
        throughput_score = min(1.0, max(0.0, (throughput_kg_h - 800.0) / 800.0))
        compliance = float(report["compliance"])
        objective = 0.40 * quality_score + 0.25 * mass_score + 0.15 * throughput_score + 0.20 * compliance
        uncertainty = 0.05 + 0.20 * (sum(1 for v in BOPET_VARIABLES if v.calibration_status != "CALIBRATED") / len(BOPET_VARIABLES))
        return EvaluationResult(
            physical_result={
                "hard_feasible": hard,
                "constraint_report": report,
                "mass_balance_residual": residual,
                "mass_tolerance": MASS_TOLERANCE,
                "missing_fields": report.get("unknown_constraints", []),
                "violated_constraints": report.get("hard_failures", []),
            },
            production_result={
                "thickness_um": thickness_um,
                "target_thickness_um": TARGET_THICKNESS_UM,
                "throughput_kg_h": throughput_kg_h,
                "calculated_mass_kg_s": calculated_mass,
                "quality_score": quality_score,
                "mass_score": mass_score,
                "throughput_score": throughput_score,
                "source": "physics proxy, not a trained production prediction",
            },
            economic_result={},
            uncertainty_result={
                "uncertainty": min(1.0, uncertainty),
                "missing_ratio": 0.0,
                "uncalibrated_ratio": sum(1 for v in BOPET_VARIABLES if v.calibration_status != "CALIBRATED") / len(BOPET_VARIABLES),
                "note": "scenario/configuration uncertainty, not a statistical CI",
            },
            hard_feasible=hard,
            soft_penalty=float(report["soft_penalty"]),
            objective_value=objective if hard else None,
            warnings=["24-variable physics proxy; no trained quality/energy model"],
            missing_fields=report.get("unknown_constraints", []),
            data_mode=self.data_mode,
        )

