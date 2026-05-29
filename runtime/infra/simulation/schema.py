"""Simulation data schemas."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SyntheticUser:
    persona_id: str
    name: str
    role: str
    behavioral_profile: dict       # e.g. {risk_tolerance: "low", verbosity: "high"}
    llm_system_prompt: str = ""    # injected as persona


@dataclass
class MockSystem:
    system_id: str
    name: str
    endpoints: dict                 # {endpoint_path: response_template}
    latency_ms: int = 500           # simulated response delay


@dataclass
class FailureInjection:
    at_step: int
    failure_type: str              # timeout | error | wrong_response | slow
    target: str                    # system or agent id


@dataclass
class SuccessCriterion:
    metric: str
    threshold: Any
    weight: float = 1.0


@dataclass
class Scenario:
    scenario_id: str
    name: str
    description: str
    synthetic_users: list[SyntheticUser]
    mock_systems: list[MockSystem]
    inject_failures: list[FailureInjection]
    success_criteria: list[SuccessCriterion]
    risk_threshold: float = 0.20    # block prod if risk > this
    max_steps: int = 50
    timeout_s: int = 300


@dataclass
class StepResult:
    step_idx: int
    action: str
    agent: Optional[str]
    ok: bool
    latency_ms: float
    output: Optional[Any]
    error: Optional[str]
    ts: float = field(default_factory=time.time)


@dataclass
class AssertionResult:
    criterion: str
    passed: bool
    actual: Any
    expected: Any
    score: float                    # 0-1


@dataclass
class RiskScore:
    scenario_id: str
    probability: float              # P(failure)
    severity_weight: float
    risk: float                     # probability × (1 + severity_weight)
    breakdown: dict = field(default_factory=dict)


@dataclass
class SimulationResult:
    run_id: str
    scenario_id: str
    status: RunStatus
    steps: list[StepResult] = field(default_factory=list)
    assertions: list[AssertionResult] = field(default_factory=list)
    overall_score: float = 0.0
    risk: Optional[RiskScore] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
