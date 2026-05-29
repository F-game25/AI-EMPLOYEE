"""Code Index API (WS4) — index a project + retrieve relevant code for codegen.

Surface for AscendForge's "understanding" layer. Node's /api/forge proxies here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/code-index", tags=["code-index"])


class IndexReq(BaseModel):
    root: str = Field(..., description="Absolute project root to index")
    project_id: str = Field(..., description="Stable id for the project's index")
    max_files: int = Field(400, ge=10, le=2000)


class ContextReq(BaseModel):
    project_id: str
    query: str
    k: int = Field(6, ge=1, le=20)


@router.post("/index")
def index(req: IndexReq):
    from core.code_indexer import index_project
    return index_project(req.root, req.project_id, max_files=req.max_files)


@router.post("/context")
def context(req: ContextReq):
    from core.code_indexer import query_context
    return query_context(req.project_id, req.query, k=req.k)


@router.get("/summary/{project_id}")
def summary(project_id: str):
    from core.code_indexer import get_summary
    return get_summary(project_id)
