from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter

from app.schemas import MetricRecord, MetricsHistoryResponse, MetricsRecordRequest, ROIResponse
from app.state import store

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("/record", response_model=MetricRecord)
def record_metrics(req: MetricsRecordRequest) -> MetricRecord:
    roi = ((req.revenue - req.cost) / req.cost) if req.cost else req.revenue
    item = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "revenue": req.revenue,
        "cost": req.cost,
        "roi": roi,
        "notes": req.notes,
    }
    store.append("metrics", item)
    return MetricRecord(**item)


@router.get("/history", response_model=MetricsHistoryResponse)
def metrics_history() -> MetricsHistoryResponse:
    items = store.read("metrics", [])
    return MetricsHistoryResponse(records=[MetricRecord(**i) for i in items])


@router.get("/roi", response_model=ROIResponse)
def roi() -> ROIResponse:
    records = store.read("metrics", [])
    total_revenue = sum(float(r.get("revenue", 0)) for r in records)
    total_cost = sum(float(r.get("cost", 0)) for r in records)
    roi_val = ((total_revenue - total_cost) / total_cost) if total_cost else total_revenue
    return ROIResponse(roi=roi_val, total_revenue=total_revenue, total_cost=total_cost)
