"""ASCEND AI — System Router"""

import os

from fastapi import APIRouter

from services.system_monitor import get_stats

router = APIRouter()


@router.get("/system/stats")
def stats():
    return get_stats()


@router.get("/health")
def health():
    mock = not os.path.exists(os.path.expanduser("~/.ai-employee"))
    return {"status": "ok", "version": "1.0.0", "mock": mock}
