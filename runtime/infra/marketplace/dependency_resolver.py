"""Semver-aware topological dependency resolver for plugins."""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _semver_satisfies(installed_version: str, required: str) -> bool:
    """Very simple semver check: installed >= required (no range operators)."""
    try:
        iv = [int(x) for x in installed_version.split(".")[:3]]
        rv = [int(x) for x in required.lstrip(">=^~").split(".")[:3]]
        return iv >= rv
    except Exception:
        return True


def resolve(plugins: list[dict], target_id: str) -> tuple[list[str], list[str]]:
    """
    Topological sort of install order for target_id + its transitive deps.
    Returns (ordered_install_list, errors).
    plugins: list of {id, version, requires: [{id, version}]}
    """
    index = {p["id"]: p for p in plugins}
    order = []
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[str] = []

    def visit(pid: str) -> None:
        if pid in visited:
            return
        if pid in visiting:
            errors.append(f"Circular dependency detected: {pid}")
            return
        visiting.add(pid)
        plugin = index.get(pid)
        if not plugin:
            errors.append(f"Plugin not found: {pid}")
            visiting.discard(pid)
            return
        for dep in plugin.get("requires", []):
            dep_id = dep["id"]
            dep_ver = dep.get("version", "0.0.0")
            if dep_id in index:
                installed_ver = index[dep_id]["version"]
                if not _semver_satisfies(installed_ver, dep_ver):
                    errors.append(
                        f"{pid} requires {dep_id}>={dep_ver} but {installed_ver} installed"
                    )
            else:
                errors.append(f"{pid} requires {dep_id} which is not available")
            visit(dep_id)
        visiting.discard(pid)
        visited.add(pid)
        order.append(pid)

    visit(target_id)
    return order, errors
