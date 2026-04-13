from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import CustomAgentRequest, SkillResponse
from app.state import store

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=list[SkillResponse])
def list_skills(category: str | None = Query(default=None), query: str | None = Query(default=None)) -> list[SkillResponse]:
    mgr = store.skills
    if category:
        items = mgr.list_by_category(category)
    elif query:
        items = mgr.search(query)
    else:
        items = mgr.list_all()
    return [SkillResponse(**i) for i in items]


@router.get("/skills/{skill_id}", response_model=SkillResponse)
def get_skill(skill_id: str) -> SkillResponse:
    item = store.skills.get(skill_id)
    if not item:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**item)


@router.post("/agents/custom")
def create_custom_agent(req: CustomAgentRequest) -> dict:
    prompt = store.skills.compose_prompt(req.skills)
    payload = {"id": req.id, "name": req.name, "skills": req.skills, "system_prompt": prompt}
    return store.skills.create_custom_agent(payload)


@router.get("/agents/custom")
def list_custom_agents() -> list[dict]:
    return store.skills.list_custom_agents()
