"""DigitalTwinManager — mock external system responses."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from .schema import MockSystem

logger = logging.getLogger(__name__)

_MOCKS_DIR = Path(__file__).parent / "scenarios" / "mocks"
_DEFAULT_LATENCIES = {
    "salesforce": 800,
    "sap": 1200,
    "jira": 300,
    "docusign": 600,
    "hubspot": 400,
    "confluence": 350,
    "sharepoint": 500,
}


def _load_mock(system_id: str) -> dict:
    f = _MOCKS_DIR / f"{system_id}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {}


class DigitalTwinManager:
    def __init__(self):
        # Keyed by (tenant_id, system_id) — prevents cross-tenant override leakage
        self._overrides: dict[tuple[str, str], dict] = {}

    def get_system(self, system_id: str, tenant_id: str = "system") -> MockSystem:
        tenant_overrides = self._overrides.get((tenant_id, system_id), {})
        endpoints = {**_load_mock(system_id), **tenant_overrides}
        return MockSystem(
            system_id=system_id,
            name=system_id.replace("-", " ").title(),
            endpoints=endpoints,
            latency_ms=_DEFAULT_LATENCIES.get(system_id, 500),
        )

    async def call(self, system_id: str, endpoint: str, payload: dict = None,
                   tenant_id: str = "system") -> dict:
        sys = self.get_system(system_id, tenant_id)
        await asyncio.sleep(sys.latency_ms / 1000)
        resp = sys.endpoints.get(endpoint)
        if resp is None:
            return {"ok": False, "error": f"endpoint {endpoint!r} not in mock for {system_id}",
                    "mock": True}
        if isinstance(resp, str):
            for k, v in (payload or {}).items():
                resp = resp.replace(f"{{{{{k}}}}}", str(v))
        return {"ok": True, "data": resp, "mock": True,
                "latency_ms": sys.latency_ms, "system": system_id}

    def configure(self, system_id: str, endpoints: dict, tenant_id: str = "system") -> None:
        self._overrides[(tenant_id, system_id)] = endpoints
        logger.info("DigitalTwin override set for %s/%s (%d endpoints)",
                    tenant_id, system_id, len(endpoints))

    def list_systems(self, tenant_id: str = "system") -> list[str]:
        built_in = list(_DEFAULT_LATENCIES.keys())
        custom = [sid for (tid, sid) in self._overrides if tid == tenant_id]
        return sorted(set(built_in + custom))


_mgr: Optional[DigitalTwinManager] = None


def get_digital_twin_manager() -> DigitalTwinManager:
    global _mgr
    if _mgr is None:
        _mgr = DigitalTwinManager()
    return _mgr
