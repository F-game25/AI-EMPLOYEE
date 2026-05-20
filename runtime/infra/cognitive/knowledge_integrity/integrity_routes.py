from fastapi import APIRouter, Request
from .lifecycle_manager import get_counts, quarantine, restore, run_decay
from .deduplicator import list_clusters, get_deduplicator
from .entropy_reducer import report as entropy_report, prune_stale, get_stats as get_entropy_stats
from .contradiction_scanner import list_contradictions
from .hallucination_detector import list_flags as list_hallucination_flags

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/status")
async def integrity_status(req: Request):
    counts = get_counts(_tenant(req))
    total = sum(counts.values())
    quarantined = counts.get("quarantined", 0)
    score = max(0.0, 100.0 - quarantined / max(total, 1) * 100)
    return {"data": {"integrity_score": round(score, 1), "total": total, "by_lifecycle": counts}}


@router.get("/lifecycle")
async def get_lifecycle(req: Request):
    return {"data": {"counts": get_counts(_tenant(req))}}


@router.post("/scan")
async def trigger_scan(req: Request):
    changed = run_decay(_tenant(req))
    return {"data": {"ok": True, "memories_transitioned": changed}}


@router.get("/duplicates")
async def get_duplicates(req: Request):
    return {"data": {"duplicates": list_clusters(_tenant(req))}}


@router.post("/quarantine/{memory_id}")
async def do_quarantine(memory_id: str, req: Request):
    quarantine(memory_id, _tenant(req))
    return {"data": {"ok": True}}


@router.post("/restore/{memory_id}")
async def do_restore(memory_id: str, req: Request):
    restore(memory_id, _tenant(req))
    return {"data": {"ok": True}}


@router.get("/report")
async def get_report(req: Request):
    return {"data": entropy_report(_tenant(req))}


@router.get("/entropy")
async def get_entropy_stats_endpoint(req: Request):
    return {"data": get_entropy_stats(_tenant(req))}


@router.get("/contradictions")
async def get_contradictions(req: Request, limit: int = 50):
    return {"data": {"contradictions": list_contradictions(_tenant(req), limit)}}


@router.get("/hallucinations")
async def get_hallucinations(req: Request, limit: int = 50):
    return {"data": {"hallucinations": list_hallucination_flags(_tenant(req), limit)}}


@router.post("/prune")
async def trigger_prune(req: Request, min_access: int = 0):
    count = prune_stale(_tenant(req), min_access)
    return {"data": {"ok": True, "pruned_count": count}}
