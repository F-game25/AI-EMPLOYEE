"""Company Manager — Multi-Company Support & Template Export/Import.

Inspired by Paperclip's multi-company model, this module enables:
  - Multiple isolated companies in one AI-EMPLOYEE deployment
  - Per-company state directories (complete data isolation)
  - Switch active company context
  - Export company configuration (agents, goals, org chart, skills, schedules)
    with automatic secret scrubbing
  - Import company templates with collision detection

State root: ~/.ai-employee/state/companies/<company_id>/
Config:     ~/.ai-employee/config/companies.json

API (via problem-solver-ui server.py):
  GET    /api/companies                  — list all companies
  POST   /api/companies                  — create a new company
  DELETE /api/companies/{id}             — delete a company
  POST   /api/companies/switch           — switch active company
  GET    /api/companies/active           — get active company
  GET    /api/companies/{id}/export      — export company (secrets scrubbed)
  POST   /api/companies/import           — import a company template
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("company-manager")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
COMPANIES_FILE = AI_HOME / "config" / "companies.json"
COMPANIES_STATE_ROOT = AI_HOME / "state" / "companies"

# Regex patterns that look like secrets (scrubbed on export).
# The patterns are intentionally conservative to avoid over-scrubbing
# legitimate identifiers (e.g., SHA hashes, UUIDs).
_SECRET_PATTERNS = [
    # Key=value pairs where the key name suggests a secret
    re.compile(r'(?i)(api[_-]?key|secret|password|token|bearer|auth)\s*[=:]\s*\S+'),
    # OpenAI / Anthropic style prefixed keys (sk-..., sk-ant-...)
    re.compile(r'\bsk-[a-zA-Z0-9]{20,}\b'),
    # Standard Bearer token patterns (eyJ... JWT tokens)
    re.compile(r'\beyJ[a-zA-Z0-9+/]{30,}'),
]
_PLACEHOLDER = "***SCRUBBED***"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Persistence ───────────────────────────────────────────────────────────────


def _load_registry() -> dict:
    if COMPANIES_FILE.exists():
        try:
            return json.loads(COMPANIES_FILE.read_text())
        except Exception as exc:
            logger.warning("companies registry load error: %s", exc)
    return {"companies": {}, "active_company_id": None}


def _save_registry(data: dict) -> None:
    COMPANIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    COMPANIES_FILE.write_text(json.dumps(data, indent=2))


# ── Company CRUD ──────────────────────────────────────────────────────────────


def create_company(
    name: str,
    description: str = "",
    mission: str = "",
    company_id: str | None = None,
) -> dict:
    """Create a new company and initialize its isolated state directory."""
    if not company_id:
        company_id = str(uuid.uuid4())[:8]
    now = _now_iso()
    company: dict = {
        "company_id": company_id,
        "name": name,
        "description": description,
        "mission": mission,
        "created_at": now,
        "updated_at": now,
    }
    # Initialize per-company state directory
    company_dir = COMPANIES_STATE_ROOT / company_id
    company_dir.mkdir(parents=True, exist_ok=True)
    # Write company manifest
    (company_dir / "manifest.json").write_text(json.dumps(company, indent=2))

    registry = _load_registry()
    registry["companies"][company_id] = company
    # If this is the first company, make it active
    if not registry.get("active_company_id"):
        registry["active_company_id"] = company_id
    _save_registry(registry)
    return company


def list_companies() -> list[dict]:
    registry = _load_registry()
    active = registry.get("active_company_id")
    result = []
    for c in registry.get("companies", {}).values():
        result.append({**c, "is_active": c["company_id"] == active})
    result.sort(key=lambda c: c.get("created_at", ""))
    return result


def get_active_company() -> dict | None:
    registry = _load_registry()
    active_id = registry.get("active_company_id")
    if active_id:
        return registry.get("companies", {}).get(active_id)
    return None


def switch_company(company_id: str) -> dict:
    """Switch the active company context."""
    registry = _load_registry()
    if company_id not in registry.get("companies", {}):
        raise ValueError(f"Company '{company_id}' not found")
    registry["active_company_id"] = company_id
    _save_registry(registry)
    return registry["companies"][company_id]


def delete_company(company_id: str) -> bool:
    registry = _load_registry()
    companies = registry.get("companies", {})
    if company_id not in companies:
        return False

    # Don't allow deleting the last company
    if len(companies) <= 1:
        raise ValueError("Cannot delete the last company")

    # If deleting active company, switch to another
    if registry.get("active_company_id") == company_id:
        other = next(cid for cid in companies if cid != company_id)
        registry["active_company_id"] = other

    del companies[company_id]
    _save_registry(registry)
    return True


def get_company_state_dir(company_id: str | None = None) -> Path:
    """Return the isolated state directory for a company.

    If company_id is None, returns the active company's state dir,
    falling back to the root state dir for backward compatibility.
    """
    if company_id is None:
        active = get_active_company()
        if active:
            company_id = active["company_id"]

    if company_id:
        path = COMPANIES_STATE_ROOT / company_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    return AI_HOME / "state"


# ── Secret scrubbing ──────────────────────────────────────────────────────────


def _scrub_value(value: str) -> str:
    """Replace secret-looking strings with a placeholder."""
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(_PLACEHOLDER, value)
    return value


def _scrub_dict(obj: object) -> object:
    """Recursively scrub secrets from a dict/list/str."""
    if isinstance(obj, dict):
        return {k: _scrub_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_dict(item) for item in obj]
    if isinstance(obj, str):
        return _scrub_value(obj)
    return obj


# ── Export / Import ───────────────────────────────────────────────────────────


def export_company(company_id: str) -> dict:
    """Export a company's full configuration with secrets scrubbed.

    Includes: company manifest, goals, org chart, skills, schedules.
    Secrets (API keys, passwords, tokens) are automatically replaced
    with '***SCRUBBED***' placeholders.
    """
    registry = _load_registry()
    company = registry.get("companies", {}).get(company_id)
    if not company:
        raise ValueError(f"Company '{company_id}' not found")

    export: dict = {
        "export_version": "1.0",
        "exported_at": _now_iso(),
        "company": _scrub_dict(company),
        "goals": {},
        "org_chart": {},
        "skills": [],
        "schedules": [],
    }

    # Goals
    goals_file = AI_HOME / "config" / "company_goals.json"
    if goals_file.exists():
        try:
            export["goals"] = _scrub_dict(json.loads(goals_file.read_text()))
        except Exception:
            pass

    # Org chart
    org_chart_file = AI_HOME / "config" / "org_chart.json"
    if org_chart_file.exists():
        try:
            export["org_chart"] = _scrub_dict(json.loads(org_chart_file.read_text()))
        except Exception:
            pass

    # Skills library
    skills_file = AI_HOME / "config" / "skills_library.json"
    if skills_file.exists():
        try:
            export["skills"] = _scrub_dict(json.loads(skills_file.read_text()))
        except Exception:
            pass

    # Schedules
    schedules_file = AI_HOME / "config" / "schedules.json"
    if schedules_file.exists():
        try:
            export["schedules"] = _scrub_dict(json.loads(schedules_file.read_text()))
        except Exception:
            pass

    return export


def import_company(template: dict, name_override: str | None = None) -> dict:
    """Import a company template exported by export_company().

    Handles collision detection by generating a new company_id.
    Returns the newly created company record.
    """
    company_data = template.get("company", {})
    name = name_override or company_data.get("name", f"Imported-{_now_iso()[:10]}")
    description = company_data.get("description", "")
    mission = company_data.get("mission", "")

    # Always generate a new ID to avoid collisions
    new_company = create_company(
        name=name,
        description=description,
        mission=mission,
    )
    new_id = new_company["company_id"]

    # Restore goals (if present and not scrubbed)
    goals = template.get("goals", {})
    if goals and goals.get("mission") and goals["mission"] != _PLACEHOLDER:
        goals_file = AI_HOME / "config" / "company_goals.json"
        try:
            goals_file.parent.mkdir(parents=True, exist_ok=True)
            goals_file.write_text(json.dumps(goals, indent=2))
        except Exception as exc:
            logger.warning("import: could not restore goals: %s", exc)

    # Restore schedules (if present)
    schedules = template.get("schedules", [])
    if schedules:
        sched_file = AI_HOME / "config" / "schedules.json"
        try:
            # Merge with existing schedules (no duplicates by task_id)
            existing: list = []
            if sched_file.exists():
                existing = json.loads(sched_file.read_text())
            existing_ids = {s.get("task_id") for s in existing}
            for s in schedules:
                if s.get("task_id") not in existing_ids:
                    existing.append(s)
            sched_file.write_text(json.dumps(existing, indent=2))
        except Exception as exc:
            logger.warning("import: could not restore schedules: %s", exc)

    logger.info("company-manager: imported company '%s' as id=%s", name, new_id)
    return new_company
