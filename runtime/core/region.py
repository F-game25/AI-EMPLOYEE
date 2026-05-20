"""Data residency — tenant-to-region mapping, enforced at every data access."""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REGIONS: dict[str, object] = {
    "eu": {
        "name": "Europe",
        "api_endpoint": os.getenv("REGION_EU_ENDPOINT", "https://eu.api.aeternus.ai"),
        "db_url_env": "DATABASE_URL_EU",
        "storage_prefix": "eu",
        "countries": ["DE", "FR", "NL", "BE", "AT", "ES", "IT", "PL", "SE", "DK", "FI", "NO"],
    },
    "us": {
        "name": "United States",
        "api_endpoint": os.getenv("REGION_US_ENDPOINT", "https://us.api.aeternus.ai"),
        "db_url_env": "DATABASE_URL_US",
        "storage_prefix": "us",
        "countries": ["US", "CA", "MX"],
    },
    "default": "us",
}

_VALID_REGIONS = {k for k in REGIONS if k != "default"}
_STATE_FILE = Path(os.getenv("AI_HOME", Path.home() / ".ai-employee")) / "state" / "tenant_regions.json"
_LOCK = threading.Lock()


class DataResidencyViolation(Exception):
    """Raised when a tenant's data is accessed in the wrong region."""


class RegionRegistry:
    """Persist and enforce tenant-to-region assignments.

    Backed by ~/.ai-employee/state/tenant_regions.json.
    Thread-safe via a module-level lock.
    """

    def __init__(self, state_file: Path = _STATE_FILE) -> None:
        self._path = state_file
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── persistence ────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self._path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self._path.write_text(json.dumps(data, indent=2))

    # ── public API ─────────────────────────────────────────────────────────────

    def assign_region(self, tenant_id: str, region: str) -> None:
        """Persist a tenant→region assignment.  Idempotent; re-assigning is an error
        only if the region *changes* (would require a data migration)."""
        if region not in _VALID_REGIONS:
            raise ValueError(f"Unknown region '{region}'. Valid: {sorted(_VALID_REGIONS)}")
        with _LOCK:
            data = self._load()
            existing = data.get(tenant_id)
            if existing and existing != region:
                raise DataResidencyViolation(
                    f"Tenant '{tenant_id}' is already assigned to region '{existing}'. "
                    f"Re-assignment to '{region}' requires an explicit data migration."
                )
            data[tenant_id] = region
            self._save(data)
        logger.info("region.assign tenant=%s region=%s", tenant_id, region)

    def get_region(self, tenant_id: str) -> str:
        """Return the assigned region, or the default region if not set."""
        with _LOCK:
            data = self._load()
        return data.get(tenant_id, str(REGIONS["default"]))

    def get_endpoint(self, tenant_id: str) -> str:
        """Return the API endpoint URL for a tenant's region."""
        region = self.get_region(tenant_id)
        return str(REGIONS[region]["api_endpoint"])  # type: ignore[index]

    def enforce(self, tenant_id: str, current_region: str) -> None:
        """Raise DataResidencyViolation if tenant's assigned region != current_region.

        current_region should come from the DEPLOYMENT_REGION env var of the running
        instance so we can reject cross-region requests at the handler level.
        """
        assigned = self.get_region(tenant_id)
        if assigned != current_region:
            raise DataResidencyViolation(
                f"Tenant '{tenant_id}' is assigned to region '{assigned}' but this "
                f"instance is running in region '{current_region}'. "
                f"Direct requests to {self.get_endpoint(tenant_id)}"
            )

    def detect_region_from_ip(self, ip: str) -> str:
        """Best-effort region detection from a client IP address.

        Strategy:
        - Private / loopback IPs → deployment default (DEPLOYMENT_REGION or "us")
        - All other IPs → same default (real geo-IP requires MaxMind GeoLite2)
        DEPLOYMENT_REGION env var overrides for the current instance.
        """
        deployment = os.getenv("DEPLOYMENT_REGION", "")
        if deployment in _VALID_REGIONS:
            return deployment
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return str(REGIONS["default"])
        except ValueError:
            pass
        return str(REGIONS["default"])


# ── singleton ──────────────────────────────────────────────────────────────────

_registry: Optional[RegionRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> RegionRegistry:
    """Return the module-level singleton RegionRegistry."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = RegionRegistry()
    return _registry
