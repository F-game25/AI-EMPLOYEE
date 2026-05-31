"""Code Index API (WS4) — index a project + retrieve relevant code for codegen.

Surface for AscendForge's "understanding" layer. Node's /api/forge proxies here.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/code-index", tags=["code-index"])
_ERROR_KEYS = {"error", "errors", "detail", "details", "exception", "traceback", "stack"}


def _public_index(value: dict) -> dict:
    if not isinstance(value, dict) or not value.get("ok"):
        return {"ok": False, "error": "index_failed"}
    return {
        "ok": True,
        "project_id": value.get("project_id", ""),
        "indexed_at": value.get("indexed_at"),
        "files": int(value.get("files", 0) or 0),
        "chunks": int(value.get("chunks", 0) or 0),
        "lines": int(value.get("lines", 0) or 0),
        "languages": value.get("languages") if isinstance(value.get("languages"), dict) else {},
        "entry_points": [str(p)[:256] for p in (value.get("entry_points") or [])[:10]],
        "top_modules": [
            {
                "path": str(item.get("path", ""))[:256],
                "symbol_count": int(item.get("symbol_count", 0) or 0),
                "symbols": [str(s)[:128] for s in (item.get("symbols") or [])[:12]],
            }
            for item in (value.get("top_modules") or [])[:15]
            if isinstance(item, dict)
        ],
        "import_edges": int(value.get("import_edges", 0) or 0),
        "duration_s": value.get("duration_s", 0),
    }


def _public_context(value: dict) -> dict:
    if not isinstance(value, dict) or not value.get("ok"):
        return {"ok": False, "error": "context_failed", "results": []}
    results = []
    for item in (value.get("results") or [])[:20]:
        if not isinstance(item, dict):
            continue
        results.append({
            "path": str(item.get("path", ""))[:256],
            "symbol": str(item.get("symbol", ""))[:128],
            "lang": str(item.get("lang", ""))[:64],
            "score": item.get("score", 0),
            "snippet": str(item.get("snippet", ""))[:1200],
        })
    return {
        "ok": True,
        "query": str(value.get("query", ""))[:500],
        "count": len(results),
        "files": [str(p)[:256] for p in (value.get("files") or [])[:50]],
        "results": results,
    }


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
    try:
        from core.code_indexer import index_project
        result = index_project(req.root, req.project_id, max_files=req.max_files)
        return _public_index(result)
    except Exception:
        logger.warning("code-index index failed")
        raise HTTPException(status_code=500, detail="Code index failed")


@router.post("/context")
def context(req: ContextReq):
    try:
        from core.code_indexer import query_context
        result = query_context(req.project_id, req.query, k=req.k)
        return _public_context(result)
    except Exception:
        logger.warning("code-index context failed")
        raise HTTPException(status_code=500, detail="Code context failed")


@router.get("/summary/{project_id}")
def summary(project_id: str):
    try:
        from core.code_indexer import get_summary
        result = get_summary(project_id)
        return _public_index(result)
    except Exception:
        logger.warning("code-index summary failed")
        raise HTTPException(status_code=500, detail="Code summary failed")
