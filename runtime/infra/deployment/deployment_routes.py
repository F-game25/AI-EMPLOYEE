"""FastAPI routes for distributed deployment — /deployment/*"""
from __future__ import annotations
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .k8s_client import get_k8s_client

logger = logging.getLogger(__name__)
router = APIRouter()

_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")


class ScaleRequest(BaseModel):
    deployment: str
    replicas: int


class BlueGreenRequest(BaseModel):
    deployment: str
    slot: str = "blue"  # blue | green


@router.get("/status")
async def deployment_status():
    k = get_k8s_client()
    deps = k.get_deployments(_NAMESPACE)
    return {"ok": True, "k8s_available": k.available(), "deployments": deps.get("deployments", [])}


@router.get("/pods")
async def list_pods():
    return get_k8s_client().get_pods(_NAMESPACE)


@router.post("/scale")
async def scale_deployment(body: ScaleRequest):
    return get_k8s_client().scale(body.deployment, body.replicas, _NAMESPACE)


@router.post("/rollback")
async def rollback(body: ScaleRequest):  # reuse ScaleRequest.deployment field
    return get_k8s_client().rollback(body.deployment, _NAMESPACE)


@router.get("/history")
async def release_history():
    # Helm history via subprocess (graceful if helm not available)
    try:
        import subprocess
        result = subprocess.run(
            ["helm", "history", "aeternus-nexus", "--output", "json"],
            capture_output=True, text=True, timeout=15
        )
        import json
        history = json.loads(result.stdout) if result.returncode == 0 else []
        return {"ok": True, "history": history}
    except Exception as e:
        logger.warning("release history failed: %s", type(e).__name__)
        return {"ok": False, "reason": "release history unavailable", "history": []}


@router.post("/blue-green")
async def blue_green_swap(body: BlueGreenRequest):
    # In real k8s: patch ingress serviceName; here return instructions
    return {
        "ok": True,
        "instruction": f"Patch ingress to route to {body.deployment}-{body.slot}",
        "kubectl_command": (
            f"kubectl patch ingress aeternus-nexus -n {_NAMESPACE} "
            f"--type json -p '[{{\"op\":\"replace\",\"path\":\"/spec/rules/0/http/paths/0/backend/service/name\","
            f"\"value\":\"{body.deployment}-{body.slot}\"}}]'"
        ),
    }


@router.get("/metrics")
async def resource_metrics():
    return get_k8s_client().get_resource_metrics(_NAMESPACE)


@router.post("/drain")
async def drain_node(req: Request):
    node = req.query_params.get("node")
    if not node:
        raise HTTPException(400, "node query param required")
    return {
        "ok": True,
        "kubectl_command": f"kubectl cordon {node} && kubectl drain {node} --ignore-daemonsets --delete-emptydir-data",
        "message": "Execute the kubectl command above to drain the node",
    }
