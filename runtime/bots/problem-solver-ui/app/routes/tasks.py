from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.schemas import GenericMessage, TaskCreateRequest, TaskResponse
from app.state import store

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
def list_tasks() -> list[TaskResponse]:
    items = store.read("tasks", [])
    return [TaskResponse(**i) for i in items]


@router.post("", response_model=TaskResponse)
def create_task(req: TaskCreateRequest) -> TaskResponse:
    item = store.create_task(req.task)
    return TaskResponse(**item)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    tasks = store.read("tasks", [])
    for item in tasks:
        if item.get("id") == task_id:
            return TaskResponse(**item)
    raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/{task_id}", response_model=GenericMessage)
def delete_task(task_id: str) -> GenericMessage:
    tasks = store.read("tasks", [])
    new_tasks = [t for t in tasks if t.get("id") != task_id]
    if len(new_tasks) == len(tasks):
        raise HTTPException(status_code=404, detail="Task not found")
    store.write("tasks", new_tasks)
    return GenericMessage(message="deleted")
