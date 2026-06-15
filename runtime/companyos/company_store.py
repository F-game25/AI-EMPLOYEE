"""CompanyStore — local-first persistence for companies/projects.

Local is the source of truth (anti-Polsia: no lock-in). Each company holds its
brief, validation verdict, status, roadmap, decisions, artifacts, and metrics.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.RLock()
_FILE = "companies.json"

# Company lifecycle. Note 'building' is only reachable after a passing validation
# verdict — enforced by CompanyOS, not just convention.
STATUSES = ("intake", "validating", "validated", "rejected", "planning",
            "building", "operating", "paused", "archived")


def _state_dir() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        return canonical_state_dir()
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parents[2] / "state"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CompanyStore:
    def __init__(self) -> None:
        self._path = _state_dir() / _FILE

    def _load(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception:  # noqa: BLE001
            return []

    def _save(self, items: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.rename(self._path)

    def create(self, *, name: str, brief: dict | None = None) -> dict:
        company = {
            "id": str(uuid.uuid4())[:8],
            "name": name or "Untitled Company",
            "status": "intake",
            "brief": brief or {},
            "validation": None,          # set by validation_engine; gates 'building'
            "roadmap": None,
            "decisions": [],             # transparent decision log (anti-Polsia)
            "artifacts": [],
            "metrics": {"revenue_cents": 0, "cost_cents": 0, "is_estimate_only": True},
            "created_at": _now(),
            "updated_at": _now(),
        }
        with _LOCK:
            items = self._load()
            items.append(company)
            self._save(items)
        return company

    def get(self, company_id: str) -> dict | None:
        return next((c for c in self._load() if c.get("id") == company_id), None)

    def list(self) -> list[dict]:
        return self._load()

    def update(self, company_id: str, patch: dict) -> dict | None:
        with _LOCK:
            items = self._load()
            c = next((x for x in items if x.get("id") == company_id), None)
            if c is None:
                return None
            if "status" in patch and patch["status"] not in STATUSES:
                raise ValueError(f"invalid status '{patch['status']}'")
            c.update(patch)
            c["updated_at"] = _now()
            self._save(items)
            return c

    def log_decision(self, company_id: str, *, what: str, why: str, by: str = "companyos") -> dict | None:
        with _LOCK:
            items = self._load()
            c = next((x for x in items if x.get("id") == company_id), None)
            if c is None:
                return None
            c.setdefault("decisions", []).append(
                {"ts": _now(), "what": what, "why": why, "by": by})
            c["updated_at"] = _now()
            self._save(items)
            return c


_instance: CompanyStore | None = None
_instance_lock = threading.Lock()


def get_company_store() -> CompanyStore:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CompanyStore()
    return _instance
