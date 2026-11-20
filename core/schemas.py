# -*- coding: utf-8 -*-
"""Typed contracts shared by the V3 engine and evaluators."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataMode(str, Enum):
    SIMULATION_ONLY = "SIMULATION_ONLY"
    LITERATURE_BASED = "LITERATURE_BASED"
    SCENARIO_ESTIMATION = "SCENARIO_ESTIMATION"
    FIELD_DATA = "FIELD_DATA"


class ConstraintStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConstraintType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"
    PERFORMANCE = "PERFORMANCE"
    DERIVED = "DERIVED"
    COUPLING = "COUPLING"


class Strategy(str, Enum):
    EXPLORE = "EXPLORE"
    EXPLOIT = "EXPLOIT"
    REPAIR = "REPAIR"
    CONSTRAINT_FOCUSED = "CONSTRAINT_FOCUSED"
    UNCERTAINTY_REDUCTION = "UNCERTAINTY_REDUCTION"
    LOCAL_REFINE = "LOCAL_REFINE"
    DIVERSIFY = "DIVERSIFY"
    STOP = "STOP"


class BaseRecord(BaseModel):
    model_config = ConfigDict(extra="allow", use_enum_values=True)


class EvidenceRecord(BaseRecord):
    evidence_id: str
    source_id: str = ""
    title: str = ""
    doi: str = ""
    source_page: int | None = None
    source_text: str = ""
    source_table: str = ""
    material: str = ""
    material_grade: str = ""
    equipment: str = ""
    experimental_conditions: dict[str, Any] = Field(default_factory=dict)
    parameter_name: str = ""
    value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    unit: str = ""
    evidence_grade: str = "C"
    verification_status: str = "UNKNOWN"
    applicability_conditions: dict[str, Any] = Field(default_factory=dict)


class DecisionVariable(BaseRecord):
    variable_id: str
    name: str
    symbol: str = ""
    unit: str = ""
    lower_bound: float
    upper_bound: float
    preferred_range: tuple[float, float] | None = None
    constraint_type: ConstraintType = ConstraintType.SOFT
    calibration_status: str = "UNCALIBRATED"
    evidence_ids: list[str] = Field(default_factory=list)
    material_conditions: dict[str, Any] = Field(default_factory=dict)
    equipment_conditions: dict[str, Any] = Field(default_factory=dict)
    adjustable: bool = True
    dependency_variables: list[str] = Field(default_factory=list)
    baseline: float | None = None


class CandidatePlan(BaseRecord):
    candidate_id: str
    iteration: int = 0
    parameters: dict[str, float] = Field(default_factory=dict)
    derived_parameters: dict[str, float] = Field(default_factory=dict)
    generation_strategy: str = "manual"
    parent_candidate_id: str | None = None
    constraint_version: str = "v3.0"
    data_mode: DataMode = DataMode.SIMULATION_ONLY
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ConstraintResult(BaseRecord):
    constraint_id: str
    constraint_type: ConstraintType
    status: ConstraintStatus
    actual_value: float | None = None
    expected_range: tuple[float, float] | None = None
    violation: float = 0.0
    penalty: float = 0.0
    safety_margin: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    calibration_status: str = "UNKNOWN"
    explanation: str = ""


class EvaluationResult(BaseRecord):
    physical_result: dict[str, Any] = Field(default_factory=dict)
    production_result: dict[str, Any] = Field(default_factory=dict)
    economic_result: dict[str, Any] = Field(default_factory=dict)
    uncertainty_result: dict[str, Any] = Field(default_factory=dict)
    hard_feasible: bool = False
    soft_penalty: float = 0.0
    objective_value: float | None = None
    objective_vector: dict[str, float] = Field(default_factory=dict)
    objective_version: str = "v3.0"
    evaluation_version: str = "v3.0"
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    data_mode: DataMode = DataMode.SIMULATION_ONLY


class OptimizationState(BaseRecord):
    iteration: int = 0
    best_candidate: CandidatePlan | None = None
    current_candidate: CandidatePlan | None = None
    recent_objectives: list[float] = Field(default_factory=list)
    feasible_candidate_ratio: float = 0.0
    hard_violation_frequency: float = 0.0
    soft_penalty_trend: list[float] = Field(default_factory=list)
    uncertainty_trend: list[float] = Field(default_factory=list)
    improvement_rate: float = 0.0
    no_improvement_rounds: int = 0
    search_diversity: float = 0.0
    current_strategy: Strategy = Strategy.EXPLORE
    state_labels: list[str] = Field(default_factory=list)


class AgentDecision(BaseRecord):
    action: Strategy
    reason: str
    state_labels: list[str] = Field(default_factory=list)
    target_variables: list[str] = Field(default_factory=list)
    search_step: float | None = None
    exploration_ratio: float | None = None
    candidate_count: int | None = None
    required_information: list[str] = Field(default_factory=list)
    stopping_reason: str | None = None
