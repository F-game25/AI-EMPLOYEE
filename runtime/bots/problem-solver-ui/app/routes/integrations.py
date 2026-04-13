from __future__ import annotations

from fastapi import APIRouter

from app.schemas import GenericMessage, IntegrationRequest, IntegrationResponse
from app.state import store

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationResponse])
def list_integrations() -> list[IntegrationResponse]:
    items = store.read("integrations", {})
    return [IntegrationResponse(name=k, connected=v.get("connected", False), config=v.get("config", {})) for k, v in items.items()]


@router.post("/{name}/connect", response_model=IntegrationResponse)
def connect_integration(name: str, req: IntegrationRequest) -> IntegrationResponse:
    items = store.read("integrations", {})
    items[name] = {"connected": True, "config": req.config}
    store.write("integrations", items)
    return IntegrationResponse(name=name, connected=True, config=req.config)


@router.delete("/{name}", response_model=GenericMessage)
def disconnect_integration(name: str) -> GenericMessage:
    items = store.read("integrations", {})
    if name in items:
        items[name]["connected"] = False
    store.write("integrations", items)
    return GenericMessage(message="disconnected")
