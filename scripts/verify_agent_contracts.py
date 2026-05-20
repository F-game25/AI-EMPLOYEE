#!/usr/bin/env python3
"""Verify the core enterprise agent contract.

Default mode checks the mission-critical agents that must be present for the
launcher, orchestration, memory, and security operating model. Use --strict to
require every configured agent to expose full enterprise metadata.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES_FILE = ROOT / "runtime" / "config" / "agent_capabilities.json"
MANIFEST_FILE = ROOT / "runtime" / "config" / "system_orchestration_manifest.json"

CORE_AGENTS = {
    "ascend-forge",
    "task-orchestrator",
    "memory",
    "blacklight-security",
}

REQUIRED_MANIFEST_FIELDS = {
    "title",
    "job_description",
    "workflows",
    "hooks",
    "allowed_models",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - CLI diagnostic should include raw failure.
        raise SystemExit(f"[FAIL] Could not read {path}: {exc}") from exc


def _non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0 and all(_non_empty(item) for item in value)
    if isinstance(value, dict):
        return len(value) > 0
    return value is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="require enterprise metadata for every configured agent")
    args = parser.parse_args()

    capabilities = _load_json(CAPABILITIES_FILE)
    manifest = _load_json(MANIFEST_FILE)
    catalog_agents = set((capabilities.get("agents") or {}).keys())
    manifest_agents = manifest.get("agents") or {}

    errors: list[str] = []
    for agent_id in sorted(CORE_AGENTS):
        if agent_id not in manifest_agents:
            errors.append(f"manifest missing core agent {agent_id!r}")

    agents_to_check = set(manifest_agents.keys()) if args.strict else CORE_AGENTS
    for agent_id in sorted(agents_to_check):
        contract = manifest_agents.get(agent_id)
        if not isinstance(contract, dict):
            errors.append(f"{agent_id}: contract must be an object")
            continue
        for field in sorted(REQUIRED_MANIFEST_FIELDS):
            if not _non_empty(contract.get(field)):
                errors.append(f"{agent_id}: missing non-empty {field}")

    for agent_id in ("ascend-forge", "task-orchestrator"):
        if agent_id not in catalog_agents:
            errors.append(f"agent_capabilities missing {agent_id!r}")

    mission = manifest.get("enterprise_upgrade_mission") or {}
    if not _non_empty(mission.get("phases")):
        errors.append("enterprise_upgrade_mission.phases must be non-empty")
    if mission.get("owner_agent") != "ascend-forge":
        errors.append("enterprise_upgrade_mission.owner_agent must be ascend-forge")

    if errors:
        print("[FAIL] Agent contract verification failed:")
        for err in errors:
            print(f" - {err}")
        return 1

    mode = "strict" if args.strict else "core"
    print(f"[OK] Agent contract verification passed ({mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
