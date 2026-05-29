"""JSON Schema validation + security scanning of plugin manifests."""
from __future__ import annotations
import json
import logging
import re
from typing import Optional

from .schema import PluginManifest

logger = logging.getLogger(__name__)

_PLATFORM_VERSION = "3.0.0"

MAX_MANIFEST_SIZE = 64 * 1024  # 64 KB hard cap

# Strict allowlist — any permission not in this set is rejected
ALLOWED_PERMISSIONS: frozenset[str] = frozenset({
    "read_tasks", "write_tasks", "read_agents",
    "read_vault", "write_vault",
    "send_notifications", "call_llm", "web_search",
})

_BLOCKED_CAPABILITIES = {"system:root", "network:unrestricted", "storage:global"}

# Compiled regexes for field format validation
_RE_NAME    = re.compile(r'^[a-z0-9-]{3,64}$')
_RE_VERSION = re.compile(r'^\d+\.\d+\.\d+$')
_RE_ENTRY   = re.compile(r'^[a-zA-Z0-9_/.-]+\.py$')

_MANIFEST_SCHEMA = {
    "required": ["manifest_version", "id", "name", "version", "author",
                 "capabilities", "requires_capabilities", "permissions",
                 "tools", "workflows", "min_platform_version", "sandbox"],
    "types": {
        "manifest_version": str, "id": str, "name": str, "version": str,
        "author": str, "capabilities": list, "requires_capabilities": list,
        "permissions": list, "tools": list, "workflows": list,
        "min_platform_version": str, "sandbox": dict,
    }
}


def _semver_gte(a: str, b: str) -> bool:
    """Return True if a >= b (semver comparison, numeric only)."""
    try:
        av = [int(x) for x in a.split(".")[:3]]
        bv = [int(x) for x in b.split(".")[:3]]
        return av >= bv
    except Exception:
        return True  # fail open on parse error — platform version check is secondary


def validate(manifest_dict: dict, raw_bytes: bytes | None = None) -> tuple[bool, list[str]]:
    """Return (valid, list_of_errors).

    Pass raw_bytes when you have the original serialised manifest and want the
    size guard enforced here rather than at the upload boundary.
    """
    errors: list[str] = []

    # Size guard
    if raw_bytes is not None and len(raw_bytes) > MAX_MANIFEST_SIZE:
        errors.append(f"Manifest exceeds {MAX_MANIFEST_SIZE // 1024} KB limit")
        return False, errors

    # Required fields
    for f in _MANIFEST_SCHEMA["required"]:
        if f not in manifest_dict:
            errors.append(f"Missing required field: {f}")

    if errors:
        return False, errors

    # Type checks
    for f, expected_type in _MANIFEST_SCHEMA["types"].items():
        val = manifest_dict.get(f)
        if val is not None and not isinstance(val, expected_type):
            errors.append(f"Field '{f}' must be {expected_type.__name__}")

    # --- name format ---
    name = manifest_dict.get("name", "")
    if not _RE_NAME.match(name):
        errors.append(
            "Field 'name' must match ^[a-z0-9-]{3,64}$ "
            "(lowercase letters, digits, hyphens; 3-64 chars)"
        )

    # --- version: strict semver ---
    version = manifest_dict.get("version", "")
    if not _RE_VERSION.match(version):
        errors.append("Field 'version' must be semver: MAJOR.MINOR.PATCH (e.g. 1.0.0)")

    # --- entry_point: safe filename, no path traversal ---
    entry = manifest_dict.get("entry_point", "plugin.py")
    if not _RE_ENTRY.match(entry) or ".." in entry:
        errors.append(
            "Field 'entry_point' must match ^[a-zA-Z0-9_/.-]+\\.py$ "
            "and must not contain '..'"
        )

    # --- permissions: strict allowlist (unknown = rejected) ---
    perms = manifest_dict.get("permissions", [])
    if not isinstance(perms, list):
        errors.append("Field 'permissions' must be a list")
    else:
        unknown = set(perms) - ALLOWED_PERMISSIONS
        if unknown:
            errors.append(
                f"Unknown/disallowed permissions: {sorted(unknown)}. "
                f"Allowed: {sorted(ALLOWED_PERMISSIONS)}"
            )

    # --- capabilities blocklist ---
    caps = set(manifest_dict.get("capabilities", []))
    blocked_caps = caps & _BLOCKED_CAPABILITIES
    if blocked_caps:
        errors.append(f"Blocked capabilities: {sorted(blocked_caps)}")

    # --- platform version compatibility ---
    min_ver = manifest_dict.get("min_platform_version", "1.0.0")
    if not _semver_gte(_PLATFORM_VERSION, min_ver):
        errors.append(f"Platform version {_PLATFORM_VERSION} < required {min_ver}")

    # --- plugin ID format (reverse-domain notation) ---
    pid = manifest_dict.get("id", "")
    if not pid or len(pid) < 3 or " " in pid:
        errors.append("Plugin ID must be non-empty, no spaces (e.g. com.vendor.name)")

    return len(errors) == 0, errors


def parse(manifest_dict: dict, raw_bytes: bytes | None = None) -> Optional[PluginManifest]:
    ok, errors = validate(manifest_dict, raw_bytes=raw_bytes)
    if not ok:
        logger.warning("Manifest validation failed: %s", errors)
        return None
    return PluginManifest(
        manifest_version=manifest_dict["manifest_version"],
        id=manifest_dict["id"],
        name=manifest_dict["name"],
        version=manifest_dict["version"],
        author=manifest_dict["author"],
        description=manifest_dict.get("description", ""),
        capabilities=manifest_dict["capabilities"],
        requires_capabilities=manifest_dict["requires_capabilities"],
        permissions=manifest_dict["permissions"],
        tools=manifest_dict["tools"],
        workflows=manifest_dict["workflows"],
        min_platform_version=manifest_dict["min_platform_version"],
        sandbox=manifest_dict["sandbox"],
        approval_required=manifest_dict.get("approval_required", True),
        entry_point=manifest_dict.get("entry_point", "plugin.py"),
    )
