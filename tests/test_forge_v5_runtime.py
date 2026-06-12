import asyncio
import json
import os
import subprocess
from pathlib import Path


def test_forge_v5_runtime_builds_brief_and_goals_without_qce(monkeypatch):
    from core.forge_v5_runtime import ForgeV5Runtime

    runtime = ForgeV5Runtime()

    async def fake_reason(**kwargs):
        return {
            "ok": False,
            "selected_mode": "stepwise",
            "model_used": None,
            "paths_considered": [],
            "fallback": True,
        }

    monkeypatch.setattr(runtime.reasoning, "reason", fake_reason)
    brief = asyncio.run(runtime.start_project_brief("Improve Forge V5 safely with approval gates", "project-1", {"name": "Test"}))
    result = asyncio.run(runtime.plan_goals(brief, {"research_pack_id": "rp-test"}))

    assert brief["project_id"] == "project-1"
    assert brief["autonomy_level"] == "prepare_only"
    assert result["goals"]
    assert all(goal["status"] == "proposed" for goal in result["goals"])
    assert all(goal["approval_required"] for goal in result["goals"])


def test_compute_router_reports_unconfigured_remote_and_api(monkeypatch):
    from core.compute_router import ComputeWorkload, get_compute_router

    monkeypatch.delenv("REMOTE_COMPUTE_HOST", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    router = get_compute_router()
    health = router.health()
    decision = router.select(ComputeWorkload(heavy=True, external_allowed=True))

    assert health["local_cpu"]["available"] is True
    assert health["remote_compute"]["available"] is False
    assert health["external_api"]["available"] is False
    assert decision.backend in {"local_cpu", "local_gpu"}


def test_forge_store_v5_json_fallback(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    script = f"""
const assert = require('assert');
process.env.FORGE_RUN_STORE = 'json';
const {{ ForgeStore }} = require({json.dumps(str(repo / 'backend/services/forge_store.js'))});
const store = new ForgeStore({{ forgeHome: {json.dumps(str(tmp_path))}, maxRuns: 10 }});
store.upsertV5Artifact({{ artifact_id: 'a1', project_id: 'p1', artifact_type: 'brief', payload: {{ title: 'Brief' }} }});
store.upsertV5Goal({{ goal_id: 'g1', project_id: 'p1', title: 'Goal', description: 'Do it', priority: 90 }});
store.upsertV5QualityGate({{ quality_gate_id: 'q1', goal_id: 'g1', project_id: 'p1', status: 'partial' }});
assert.strictEqual(store.getV5Artifact('p1', 'brief').payload.title, 'Brief');
assert.strictEqual(store.getV5Goals('p1')[0].goal_id, 'g1');
assert.strictEqual(store.getV5QualityGate('g1').quality_gate_id, 'q1');
"""
    env = {**os.environ, "FORGE_RUN_STORE": "json"}
    result = subprocess.run(["node", "-e", script], cwd=repo, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
