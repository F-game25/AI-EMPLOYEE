"""ScenarioOrchestrator — load and run simulation scenarios."""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from .schema import (FailureInjection, RunStatus, Scenario, SimulationResult,
                     StepResult, SuccessCriterion, SyntheticUser, MockSystem)
from .digital_twin_manager import get_digital_twin_manager
from .evaluation_engine import EvaluationEngine
from .risk_scorer import score as risk_score

logger = logging.getLogger(__name__)

_SCENARIOS_DIR = Path(__file__).parent / "scenarios"
_eval = EvaluationEngine()


def _load_scenario_file(scenario_id: str) -> Optional[Scenario]:
    """Load scenario from YAML file."""
    try:
        import yaml
        f = _SCENARIOS_DIR / f"{scenario_id}.yaml"
        if not f.exists():
            return None
        data = yaml.safe_load(f.read_text())
        return _parse_scenario(data)
    except Exception as e:
        logger.warning("Failed to load scenario %s: %s", scenario_id, e)
        return None


def _parse_scenario(data: dict) -> Scenario:
    users = [
        SyntheticUser(
            persona_id=u.get("persona", "end_user"),
            name=u.get("name", u.get("persona", "User")),
            role=u.get("role", u.get("persona", "user")),
            behavioral_profile=u.get("profile", {}),
            llm_system_prompt=u.get("system_prompt", ""),
        )
        for u in data.get("synthetic_users", [])
    ]
    mock_systems = [
        MockSystem(system_id=s, name=s, endpoints={}, latency_ms=500)
        for s in data.get("mock_systems", [])
    ]
    failures = [
        FailureInjection(
            at_step=f["at_step"],
            failure_type=f.get("type", "error"),
            target=f.get("target", "unknown"),
        )
        for f in data.get("inject_failures", [])
    ]
    criteria = [
        SuccessCriterion(
            metric=c["metric"],
            threshold=c["threshold"],
            weight=c.get("weight", 1.0),
        )
        for c in data.get("success_criteria", [])
    ]
    return Scenario(
        scenario_id=data["scenario_id"],
        name=data.get("name", data["scenario_id"]),
        description=data.get("description", ""),
        synthetic_users=users,
        mock_systems=mock_systems,
        inject_failures=failures,
        success_criteria=criteria,
        risk_threshold=data.get("risk_threshold", 0.20),
        max_steps=data.get("max_steps", 50),
        timeout_s=data.get("timeout_s", 300),
    )


# In-memory run store — keyed by run_id (globally unique UUID, tenant encoded in result)
_runs: dict[str, SimulationResult] = {}


def list_scenarios() -> list[dict]:
    scenarios = []
    for f in sorted(_SCENARIOS_DIR.glob("*.yaml")):
        try:
            import yaml
            data = yaml.safe_load(f.read_text())
            scenarios.append({
                "scenario_id": data.get("scenario_id", f.stem),
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "mock_systems": data.get("mock_systems", []),
                "risk_threshold": data.get("risk_threshold", 0.20),
            })
        except Exception:
            pass
    return scenarios


async def run_scenario(scenario_id: str, tenant_id: str = "system",
                       run_id: str | None = None) -> SimulationResult:
    if run_id is None:
        run_id = str(uuid.uuid4())
    scenario = _load_scenario_file(scenario_id)
    if scenario is None:
        result = SimulationResult(
            run_id=run_id, scenario_id=scenario_id,
            status=RunStatus.FAILED, error="scenario_not_found",
        )
        _runs[run_id] = result
        return result

    result = SimulationResult(
        run_id=run_id, scenario_id=scenario_id, status=RunStatus.RUNNING
    )
    _runs[run_id] = result

    twin = get_digital_twin_manager()
    failure_idx = {f.at_step: f for f in scenario.inject_failures}

    try:
        async with asyncio.timeout(scenario.timeout_s):
            for step_idx in range(scenario.max_steps):
                t0 = time.time()
                failure = failure_idx.get(step_idx)

                if failure:
                    # Inject failure
                    await asyncio.sleep(0.05)
                    step = StepResult(
                        step_idx=step_idx,
                        action=f"call_{failure.target}",
                        agent=None,
                        ok=False,
                        latency_ms=(time.time() - t0) * 1000,
                        output=None,
                        error=f"injected_{failure.failure_type}",
                    )
                elif scenario.mock_systems:
                    # Call first mock system as representative step
                    svc = scenario.mock_systems[step_idx % len(scenario.mock_systems)].system_id
                    resp = await twin.call(svc, "/api/query", {"step": step_idx},
                                          tenant_id=tenant_id)
                    step = StepResult(
                        step_idx=step_idx,
                        action=f"call_{svc}",
                        agent=None,
                        ok=resp.get("ok", False),
                        latency_ms=(time.time() - t0) * 1000,
                        output=resp,
                        error=resp.get("error"),
                    )
                else:
                    # No mock systems — simulate a generic successful step
                    await asyncio.sleep(0.01)
                    step = StepResult(
                        step_idx=step_idx, action="noop", agent=None,
                        ok=True, latency_ms=(time.time() - t0) * 1000,
                        output=None, error=None,
                    )

                result.steps.append(step)

        result = _eval.evaluate(scenario, result)
        result.status = RunStatus.COMPLETED
        rs = risk_score(scenario_id, result)
        result.risk = rs

    except asyncio.TimeoutError:
        result.status = RunStatus.FAILED
        result.error = "timeout"
        result.completed_at = time.time()
    except Exception as e:
        result.status = RunStatus.FAILED
        result.error = str(e)
        result.completed_at = time.time()

    _eval.persist(result)
    _runs[run_id] = result
    return result


def get_run(run_id: str) -> Optional[SimulationResult]:
    return _runs.get(run_id)
