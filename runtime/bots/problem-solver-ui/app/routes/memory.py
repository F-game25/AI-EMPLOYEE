from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException

from app.schemas import MemoryClientRequest, MemoryClientResponse
from app.state import store

router = APIRouter(prefix="/memory/clients", tags=["memory"])


@router.get("", response_model=list[MemoryClientResponse])
def list_clients() -> list[MemoryClientResponse]:
    return [MemoryClientResponse(**x) for x in store.read("memory_clients", [])]


@router.post("", response_model=MemoryClientResponse)
def create_client(req: MemoryClientRequest) -> MemoryClientResponse:
    item = {"id": str(uuid.uuid4()), "name": req.name, "metadata": req.metadata}
    store.append("memory_clients", item)
    return MemoryClientResponse(**item)


@router.get("/{client_id}", response_model=MemoryClientResponse)
def get_client(client_id: str) -> MemoryClientResponse:
    for item in store.read("memory_clients", []):
        if item.get("id") == client_id:
            return MemoryClientResponse(**item)
    raise HTTPException(status_code=404, detail="Client not found")
