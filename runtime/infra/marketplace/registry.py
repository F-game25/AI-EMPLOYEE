"""SQLite plugin registry — install, enable, disable, uninstall."""
from __future__ import annotations
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from .schema import (ApprovalRequest, ApprovalStatus, InstalledPlugin,
                     PluginManifest, PluginStatus)
from .manifest_validator import parse as parse_manifest

logger = logging.getLogger(__name__)

_DB = Path(os.path.expanduser("~/.ai-employee/marketplace.db"))
_PLUGINS_DIR = Path(os.path.expanduser("~/.ai-employee/plugins"))
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def _safe_component(value: str, label: str) -> str:
    if not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("""
        CREATE TABLE IF NOT EXISTS plugins (
            id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            manifest TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'installed',
            package_path TEXT NOT NULL,
            installed_at REAL NOT NULL,
            enabled_at REAL,
            error TEXT,
            PRIMARY KEY (id, tenant_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS plugin_capabilities (
            plugin_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            capability TEXT NOT NULL,
            PRIMARY KEY (plugin_id, tenant_id, capability)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS plugin_approvals (
            approval_id TEXT PRIMARY KEY,
            plugin_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            resolved_at REAL,
            resolver TEXT,
            notes TEXT NOT NULL DEFAULT ''
        )
    """)
    c.commit()
    return c


class PluginRegistry:
    def install_from_bytes(self, package_bytes: bytes, tenant_id: str,
                           requested_by: str = "system") -> dict:
        """Install a .aiepkg (zip) from bytes. Returns install result."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(package_bytes))
        except Exception as e:
            return {"ok": False, "error": f"Invalid package: {e}"}

        # Read manifest
        try:
            manifest_data = json.loads(zf.read("manifest.json"))
        except Exception as e:
            return {"ok": False, "error": f"Missing/invalid manifest.json: {e}"}

        manifest = parse_manifest(manifest_data)
        if not manifest:
            from .manifest_validator import validate
            _, errors = validate(manifest_data)
            return {"ok": False, "error": "Manifest validation failed", "details": errors}

        # Verify SHA-256 BEFORE extraction
        try:
            sha_entry = zf.read("MANIFEST.sha256").decode().strip()
            actual = hashlib.sha256(package_bytes).hexdigest()
            if sha_entry != actual:
                return {"ok": False, "error": "Package checksum mismatch"}
        except KeyError:
            pass  # MANIFEST.sha256 is optional

        # Validate all archive member paths before extraction (prevent zip slip)
        plugins_root = os.path.realpath(_PLUGINS_DIR)
        plugin_dir = os.path.realpath(os.path.join(
            plugins_root,
            _safe_component(tenant_id, "tenant_id"),
            _safe_component(manifest.id, "plugin_id"),
        ))
        if os.path.commonpath([plugins_root, plugin_dir]) != plugins_root:
            return {"ok": False, "error": "Plugin path escapes plugin root"}
        plugin_dir = Path(plugin_dir)
        for member in zf.infolist():
            # Reject absolute paths and traversal sequences
            if member.filename.startswith("/") or member.filename.startswith("\\"):
                return {"ok": False, "error": f"Invalid archive path: {member.filename}"}
            member_path = (plugin_dir / member.filename).resolve()
            try:
                member_path.relative_to(plugin_dir)
            except ValueError:
                return {"ok": False, "error": f"Path traversal detected: {member.filename}"}

        plugin_dir.mkdir(parents=True, exist_ok=True)
        zf.extractall(str(plugin_dir))

        now = time.time()
        status = PluginStatus.PENDING_APPROVAL if manifest.approval_required else PluginStatus.INSTALLED

        with _conn() as c:
            c.execute("""
                INSERT INTO plugins (id,tenant_id,manifest,status,package_path,installed_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(id,tenant_id) DO UPDATE SET
                  manifest=excluded.manifest, status=excluded.status,
                  package_path=excluded.package_path, installed_at=excluded.installed_at
            """, (manifest.id, tenant_id, json.dumps(manifest_data),
                  status.value, str(plugin_dir), now))
            c.execute("DELETE FROM plugin_capabilities WHERE plugin_id=? AND tenant_id=?",
                      (manifest.id, tenant_id))
            for cap in manifest.capabilities:
                c.execute("INSERT INTO plugin_capabilities VALUES (?,?,?)",
                          (manifest.id, tenant_id, cap))

        result = {"ok": True, "plugin_id": manifest.id, "status": status.value,
                  "approval_required": manifest.approval_required}

        if manifest.approval_required:
            approval = self.create_approval(manifest.id, tenant_id, requested_by)
            result["approval_id"] = approval.approval_id

        return result

    def create_approval(self, plugin_id: str, tenant_id: str, requested_by: str) -> ApprovalRequest:
        ar = ApprovalRequest(
            approval_id=str(uuid.uuid4()),
            plugin_id=plugin_id,
            tenant_id=tenant_id,
            requested_by=requested_by,
        )
        with _conn() as c:
            c.execute("""
                INSERT INTO plugin_approvals
                  (approval_id,plugin_id,tenant_id,requested_by,status,created_at)
                VALUES (?,?,?,?,?,?)
            """, (ar.approval_id, ar.plugin_id, ar.tenant_id,
                  ar.requested_by, ar.status.value, ar.created_at))
        return ar

    def resolve_approval(self, approval_id: str, approved: bool,
                         resolver: str, notes: str = "") -> bool:
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        now = time.time()
        with _conn() as c:
            cur = c.execute("""
                UPDATE plugin_approvals SET status=?,resolved_at=?,resolver=?,notes=?
                WHERE approval_id=? AND status='pending'
            """, (status.value, now, resolver, notes, approval_id))
            if cur.rowcount == 0:
                return False
            # Update plugin status if approved
            if approved:
                row = c.execute("SELECT plugin_id,tenant_id FROM plugin_approvals WHERE approval_id=?",
                                (approval_id,)).fetchone()
                if row:
                    c.execute("UPDATE plugins SET status=? WHERE id=? AND tenant_id=?",
                              (PluginStatus.INSTALLED.value, row[0], row[1]))
        return True

    def enable(self, plugin_id: str, tenant_id: str) -> bool:
        with _conn() as c:
            cur = c.execute(
                "UPDATE plugins SET status=?,enabled_at=? WHERE id=? AND tenant_id=? AND status='installed'",
                (PluginStatus.ENABLED.value, time.time(), plugin_id, tenant_id)
            )
        return cur.rowcount > 0

    def disable(self, plugin_id: str, tenant_id: str) -> bool:
        with _conn() as c:
            cur = c.execute(
                "UPDATE plugins SET status=? WHERE id=? AND tenant_id=? AND status='enabled'",
                (PluginStatus.DISABLED.value, plugin_id, tenant_id)
            )
        return cur.rowcount > 0

    def uninstall(self, plugin_id: str, tenant_id: str) -> bool:
        with _conn() as c:
            cur = c.execute("DELETE FROM plugins WHERE id=? AND tenant_id=?",
                            (plugin_id, tenant_id))
            c.execute("DELETE FROM plugin_capabilities WHERE plugin_id=? AND tenant_id=?",
                      (plugin_id, tenant_id))
        return cur.rowcount > 0

    def list_plugins(self, tenant_id: str) -> list[dict]:
        with _conn() as c:
            rows = c.execute(
                "SELECT id,status,installed_at,enabled_at,error FROM plugins WHERE tenant_id=?",
                (tenant_id,)
            ).fetchall()
        result = []
        for r in rows:
            manifest_row = _conn().execute(
                "SELECT manifest FROM plugins WHERE id=? AND tenant_id=?", (r[0], tenant_id)
            ).fetchone()
            m = json.loads(manifest_row[0]) if manifest_row else {}
            result.append({
                "plugin_id": r[0], "name": m.get("name", r[0]),
                "version": m.get("version", "?"), "status": r[1],
                "installed_at": r[2], "enabled_at": r[3], "error": r[4],
            })
        return result

    def get_plugin(self, plugin_id: str, tenant_id: str) -> Optional[dict]:
        with _conn() as c:
            row = c.execute(
                "SELECT manifest,status,package_path,installed_at FROM plugins WHERE id=? AND tenant_id=?",
                (plugin_id, tenant_id)
            ).fetchone()
        if not row:
            return None
        m = json.loads(row[0])
        return {"plugin_id": plugin_id, "manifest": m, "status": row[1],
                "package_path": row[2], "installed_at": row[3]}

    def list_approvals(self, tenant_id: str, status: str = "pending") -> list[dict]:
        with _conn() as c:
            rows = c.execute(
                "SELECT approval_id,plugin_id,requested_by,status,created_at,notes FROM plugin_approvals "
                "WHERE tenant_id=? AND status=? ORDER BY created_at DESC",
                (tenant_id, status)
            ).fetchall()
        return [{"approval_id": r[0], "plugin_id": r[1], "requested_by": r[2],
                 "status": r[3], "created_at": r[4], "notes": r[5]} for r in rows]

    def list_capabilities(self, tenant_id: str) -> list[dict]:
        with _conn() as c:
            rows = c.execute(
                "SELECT pc.capability, pc.plugin_id, p.status FROM plugin_capabilities pc "
                "JOIN plugins p ON p.id=pc.plugin_id AND p.tenant_id=pc.tenant_id "
                "WHERE pc.tenant_id=?", (tenant_id,)
            ).fetchall()
        return [{"capability": r[0], "plugin_id": r[1], "plugin_status": r[2]} for r in rows]


_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
