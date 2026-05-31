from fastapi import APIRouter, Request
from .graph_partitioner import get_graph_partitioner
from .memory_compactor import get_memory_compactor
from .ws_batcher import get_ws_batcher
from .event_compressor import get_event_compressor
from .adaptive_cache import get_adaptive_cache

router = APIRouter()


def _tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", None) or req.headers.get("X-Tenant-Id", "system")


@router.get("/metrics")
async def get_scale_metrics(req: Request):
    cache = get_adaptive_cache()
    compressor = get_event_compressor()
    batcher = get_ws_batcher()
    return {
        "cache_metrics": cache.get_metrics(),
        "compression_stats": compressor.get_stats(),
        "ws_batch_metrics": batcher.get_metrics(),
    }


@router.post("/compact-memory")
async def compact_memory(req: Request):
    compactor = get_memory_compactor()
    stats = await compactor.compact_memories()
    return stats


@router.post("/partition-graph")
async def partition_graph(req: Request):
    tenant_id = _tenant(req)
    partitioner = get_graph_partitioner()
    result = partitioner.try_partition_neo4j(tenant_id, 60000)
    if result:
        return result
    return {"status": "no_partitioning_needed"}


@router.get("/ws-stats")
async def get_ws_stats(req: Request):
    batcher = get_ws_batcher()
    return batcher.get_metrics()


@router.get("/compression-stats")
async def get_compression_stats(req: Request):
    compressor = get_event_compressor()
    return compressor.get_stats()
