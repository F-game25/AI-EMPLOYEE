#!/usr/bin/env python3
"""Verify native fork integration metadata before packaging."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "runtime" / "config" / "fork_integration_manifest.json"
SOURCE_TRUST_PATH = REPO_ROOT / "runtime" / "config" / "source_trust.json"
SKILLS_LIBRARY_PATH = REPO_ROOT / "runtime" / "config" / "skills_library.json"
MANIFEST_DIR = REPO_ROOT / "runtime" / "vendor" / "manifests"
REQUIRED_FIELDS = {
    "id",
    "source_url",
    "fork_url",
    "upstream_commit",
    "license",
    "checksum_sha256",
    "local_namespace",
    "risk_class",
    "runtime_code_imported",
    "approval_policy",
}
FORBIDDEN_ENABLE_FLAGS = {
    "external_marketplaces_enabled",
    "external_delivery_enabled",
}
FORBIDDEN_CAPABILITIES = {
    "autonomous_wallet",
    "self_replication",
    "domain_purchase",
    "uncontrolled_self_modification",
    "coordinated_ddos",
    "credential_harvesting",
}
FORK_SOURCE_PACKS = {
    "agent-skills",
    "financial-services",
    "cashclaw",
    "automaton",
    "wallet-vault",
    "openclaw",
}
REQUIRED_SKILL_FIELDS = {
    "id",
    "source_pack",
    "source_url",
    "source_commit",
    "license",
    "risk_level",
    "approval_policy",
    "execution_steps",
    "quality_standards",
    "verification_gates",
    "compatible_agents",
    "system_prompt",
}


def fail(message: str) -> None:
    print(f"[x] {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        fail(f"missing or empty JSON file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON in {path}: {exc}")


def verify_manifest(path: Path) -> dict:
    data = load_json(path)
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        fail(f"{path.name} missing required fields: {', '.join(missing)}")
    if data["license"] not in {"MIT", "Apache-2.0"}:
        fail(f"{path.name} has unapproved license: {data['license']}")
    if len(str(data["checksum_sha256"])) != 64:
        fail(f"{path.name} checksum must be sha256 hex")
    if data["runtime_code_imported"] and not data.get("imported_paths"):
        fail(f"{path.name} imports runtime code without imported_paths")
    if not str(data["local_namespace"]).startswith("aeternus_"):
        fail(f"{path.name} namespace must be renamed under aeternus_*")
    return data


def iter_canonical_skill_ids(config: dict) -> set[str]:
    ids: set[str] = set()
    for item in config.get("engineering_skills", []):
        if item.get("canonical_skill_id"):
            ids.add(item["canonical_skill_id"])
    for item in config.get("finance_workflows", []):
        if item.get("canonical_skill_id"):
            ids.add(item["canonical_skill_id"])
    for section in ("money_mode", "autonomy_policy", "wallet_vault", "channels"):
        payload = config.get(section, {})
        for skill_id in payload.get("canonical_skill_ids", []):
            ids.add(skill_id)
    return ids


def verify_skills_library(config: dict) -> int:
    library = load_json(SKILLS_LIBRARY_PATH)
    skills = library.get("skills", [])
    if not isinstance(skills, list) or not skills:
        fail("skills_library.json has no skills")

    ids = [skill.get("id") for skill in skills]
    duplicates = sorted({skill_id for skill_id in ids if ids.count(skill_id) > 1})
    if duplicates:
        fail(f"duplicate skill IDs in skills_library.json: {', '.join(duplicates[:10])}")

    declared_total = library.get("_meta", {}).get("total_skills")
    if declared_total != len(skills):
        fail(f"skills_library.json _meta.total_skills={declared_total} but actual={len(skills)}")

    by_id = {skill["id"]: skill for skill in skills}
    missing = sorted(iter_canonical_skill_ids(config) - set(by_id))
    if missing:
        fail(f"fork manifest references skills missing from global library: {', '.join(missing[:10])}")

    imported = [skill for skill in skills if skill.get("source_pack") in FORK_SOURCE_PACKS]
    if not imported:
        fail("global skills library contains no fork-derived skills")

    for skill in imported:
        missing_fields = sorted(REQUIRED_SKILL_FIELDS - set(skill))
        if missing_fields:
            fail(f"skill {skill.get('id')} missing fields: {', '.join(missing_fields)}")
        if skill["license"] not in {"MIT", "Apache-2.0", "Owner-controlled native policy", "AETERNUS-INTERNAL"}:
            fail(f"skill {skill['id']} has unapproved license: {skill['license']}")
        if not skill.get("approval_policy"):
            fail(f"skill {skill['id']} missing approval policy")
        if not skill.get("verification_gates"):
            fail(f"skill {skill['id']} missing verification gates")

    return len(imported)


def main() -> int:
    config = load_json(CONFIG_PATH)
    source_trust = load_json(SOURCE_TRUST_PATH)
    if source_trust.get("fork_integrations", {}).get("policy") != "metadata_checked_native_enhancement":
        fail("source_trust.json missing fork integration policy")

    policy = config.get("policy", {})
    for flag in FORBIDDEN_ENABLE_FLAGS:
        if policy.get(flag) is True:
            fail(f"forbidden integration flag enabled: {flag}")

    capabilities = set(config.get("autonomy_policy", {}).get("forbidden_capabilities", []))
    missing_forbidden = sorted(FORBIDDEN_CAPABILITIES - capabilities)
    if missing_forbidden:
        fail(f"autonomy policy missing forbidden capabilities: {', '.join(missing_forbidden)}")

    manifests = sorted(MANIFEST_DIR.glob("*.json"))
    if not manifests:
        fail("no vendor intake manifests found")
    loaded = [verify_manifest(path) for path in manifests]

    source_ids = {item.get("id") for item in config.get("sources", [])}
    manifest_ids = {item.get("id") for item in loaded}
    if source_ids != manifest_ids:
        fail(f"source/manifest mismatch: sources={sorted(source_ids)} manifests={sorted(manifest_ids)}")

    if not config.get("engineering_skills"):
        fail("no engineering skills imported")
    if not config.get("finance_workflows"):
        fail("no finance workflows imported")
    if not config.get("money_mode", {}).get("approval_gates"):
        fail("money mode approval gates missing")
    wallet = config.get("wallet_vault", {})
    if wallet.get("autonomous_spending") is True:
        fail("wallet vault may not allow autonomous spending")
    if wallet.get("purchase_policy", {}).get("external_compute_enabled") is True:
        fail("external compute purchase must be disabled by default")
    if "buy_external_compute" not in set(wallet.get("approval_gates", [])):
        fail("wallet vault must require approval for external compute purchases")
    imported_skill_count = verify_skills_library(config)

    print(
        f"[OK] Vendor intake OK ({len(loaded)} sources, "
        f"{len(config['engineering_skills'])} engineering skills, "
        f"{imported_skill_count} global fork skills)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
