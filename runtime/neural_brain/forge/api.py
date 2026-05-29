"""Neural Brain Forge API — all operations delegate through ConsciousnessEngine kernel."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

forge_router = APIRouter(prefix="/forge", tags=["neural-brain-forge"])
forge_compat_router = APIRouter(prefix="/api/forge", tags=["neural-brain-forge-compat"])
logger = logging.getLogger(__name__)


class ForgeSubmitRequest(BaseModel):
    goal: str = Field(..., description="Natural-language goal or change description")
    module: str = Field(default="", description="Optional target module path")
    priority: int = Field(default=5, ge=1, le=10)
    code: str = Field(default="", description="Optional explicit code payload for ForgeController")


class ForgeApproveRequest(BaseModel):
    notes: str = Field(default="")


class BuilderRequest(BaseModel):
    spec: str = Field(..., description="Natural-language project description")
    project_name: str = Field(..., description="Directory name for generated project")
    target_type: str = Field(default="fastapi_app", description="fastapi_app|workflow|agent|frontend_page")


class ForgeChatRequest(BaseModel):
    session_id: str = ""
    project_id: str = ""
    provider: str = "local"
    message: str = Field(..., description="User instruction for AscendForge")
    history: list[dict] = Field(default_factory=list)


class ForgeActionApprovalRequest(BaseModel):
    session_id: str = ""
    ownerApproved: bool = False
    approval: str = ""


def _server_error(operation: str, exc: Exception) -> HTTPException:
    logger.warning("forge API %s failed: %s", operation, type(exc).__name__)
    return HTTPException(status_code=500, detail=f"{operation} failed")


def _skill_recommendations(message: str) -> list[dict]:
    try:
        from pathlib import Path
        import json
        skills_file = Path(__file__).resolve().parents[2] / "config" / "skills_library.json"
        data = json.loads(skills_file.read_text(encoding="utf-8"))
        terms = {term for term in message.lower().replace("-", " ").split() if len(term) > 2}
        ranked = []
        for skill in data.get("skills", []):
            text = " ".join(str(skill.get(k, "")) for k in ("id", "name", "category", "description", "source_pack")).lower()
            text += " " + " ".join(str(t) for t in skill.get("tags", []))
            score = sum(2 for term in terms if term in text)
            if skill.get("source_pack") == "agent-skills":
                score += 2
            if score > 0:
                ranked.append({**skill, "score": score})
        return sorted(ranked, key=lambda item: (-item.get("score", 0), item.get("id", "")))[:6]
    except Exception:
        return []


async def _chat(req: ForgeChatRequest) -> dict:
    skills = _skill_recommendations(req.message)
    reply = (
        "AscendForge staged this request through the supervised builder path. "
        "Recommended skills: "
        + (", ".join(skill.get("name", skill.get("id", "")) for skill in skills) or "default supervised builder skill pack")
        + ". File writes, shell commands, installs, external delivery, wallet, and compute actions require approval."
    )
    return {
        "ok": True,
        "state": "live",
        "reply": reply,
        "actions": [],
        "recommendedSkills": skills,
        "approval_policy": {
            "file_write": "approval_required",
            "shell_command": "approval_required",
            "dependency_install": "approval_required",
            "external_delivery": "approval_required",
            "wallet_or_compute": "owner_approval_required",
        },
    }


async def _approve_action(action_id: str, req: ForgeActionApprovalRequest) -> dict:
    approved = req.ownerApproved is True or req.approval == "owner-approved"
    return {
        "ok": approved,
        "state": "live" if approved else "disabled",
        "action_id": action_id,
        "approval_required": not approved,
        "output": "Action approved for supervised execution." if approved else "Owner approval required before execution.",
        "diff": None,
    }


# ── Forge Queue routes ────────────────────────────────────────────────────────

@forge_router.get("/queue")
async def get_forge_queue(status: str | None = Query(None)):
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().forge_list(status=status)
    except Exception as e:
        raise _server_error("queue list", e)


@forge_router.post("/submit")
async def submit_forge_goal(req: ForgeSubmitRequest):
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().forge_submit(goal=req.goal, module=req.module, priority=req.priority, code=req.code)
    except Exception as e:
        raise _server_error("goal submission", e)


@forge_router.post("/approve/{snapshot_id}")
async def approve_forge_item(snapshot_id: str, req: ForgeApproveRequest = None):
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().forge_approve(snapshot_id)
    except Exception as e:
        raise _server_error("approval", e)


@forge_router.post("/reject/{snapshot_id}")
async def reject_forge_item(snapshot_id: str):
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().forge_reject(snapshot_id)
    except Exception as e:
        raise _server_error("rejection", e)


# ── Evolution Status routes ───────────────────────────────────────────────────

@forge_router.get("/evolution/status")
async def get_evolution_status():
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().evolution_status()
    except Exception as e:
        raise _server_error("evolution status", e)


@forge_router.post("/evolution/mode")
async def set_evolution_mode(mode: str = Query(..., description="AUTO|SAFE|OFF")):
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().evolution_set_mode(mode)
    except Exception as e:
        raise _server_error("evolution mode", e)


# ── Builder routes ────────────────────────────────────────────────────────────

@forge_router.post("/builder/generate")
async def builder_generate(req: BuilderRequest):
    try:
        from neural_brain.core.consciousness_engine import get_engine
        return get_engine().forge_build(
            spec=req.spec,
            project_name=req.project_name,
            target_type=req.target_type,
        )
    except Exception as e:
        raise _server_error("builder generation", e)


@forge_router.post("/chat")
async def forge_chat(req: ForgeChatRequest):
    return await _chat(req)


@forge_router.post("/actions/{action_id}/approve")
async def forge_action_approve(action_id: str, req: ForgeActionApprovalRequest):
    result = await _approve_action(action_id, req)
    if not result["ok"]:
        raise HTTPException(status_code=403, detail=result)
    return result


@forge_compat_router.post("/chat")
async def forge_compat_chat(req: ForgeChatRequest):
    return await _chat(req)


@forge_compat_router.post("/actions/{action_id}/approve")
async def forge_compat_action_approve(action_id: str, req: ForgeActionApprovalRequest):
    result = await _approve_action(action_id, req)
    if not result["ok"]:
        raise HTTPException(status_code=403, detail=result)
    return result
