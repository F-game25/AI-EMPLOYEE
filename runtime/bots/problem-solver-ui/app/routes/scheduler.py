from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException

from app.schemas import GenericMessage, ScheduleRequest, ScheduleResponse
from app.state import store

router = APIRouter(prefix="/schedules", tags=["scheduler"])


@router.get("", response_model=list[ScheduleResponse])
def list_schedules() -> list[ScheduleResponse]:
    return [ScheduleResponse(**x) for x in store.read("schedules", [])]


@router.post("", response_model=ScheduleResponse)
def create_schedule(req: ScheduleRequest) -> ScheduleResponse:
    item = {"id": str(uuid.uuid4()), "name": req.name, "cron": req.cron, "payload": req.payload}
    store.append("schedules", item)
    return ScheduleResponse(**item)


@router.delete("/{schedule_id}", response_model=GenericMessage)
def delete_schedule(schedule_id: str) -> GenericMessage:
    items = store.read("schedules", [])
    new_items = [i for i in items if i.get("id") != schedule_id]
    if len(items) == len(new_items):
        raise HTTPException(status_code=404, detail="Schedule not found")
    store.write("schedules", new_items)
    return GenericMessage(message="deleted")
