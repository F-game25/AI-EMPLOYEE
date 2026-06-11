"""Filesystem-style context tree (OpenViking paradigm, rebuilt natively).

Nodes are JSON files mirroring a logical layout:

    /project/{goals,decisions,tasks,code,skills,memory,reports,feedback}
    /user/{preferences,goals,constraints}

Disk layout: ``<root>/<tenant>/<logical path>.json`` where ``<root>`` is
``$CONTEXT_DB_DIR`` (test override) → ``$STATE_DIR/context_db`` →
``~/.ai-employee/state/context_db``. Directories are plain directories.

Each node::

    {id, path, content, summary, metadata, created_at, updated_at}

- ``id`` is a stable hash of ``tenant:path`` (turbovec stable-ID pattern):
  rewrites to the same path keep the same id; ``move`` re-derives it.
- ``summary`` is a cheap first-sentences extract generated on write — this
  is the L0 tier the loader/retriever serve without touching full content.

Path safety: every public call goes through
``context_permissions.normalize_path`` (no traversal, allowlisted roots)
plus a resolved-path containment check against the tenant root.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from memory.context_db import context_permissions as perms

_LOCK = threading.RLock()
_SUMMARY_CHARS = 200
_NODE_SUFFIX = ".json"

CANONICAL_LAYOUT = (
    "/project/goals", "/project/decisions", "/project/tasks", "/project/code",
    "/project/skills", "/project/memory", "/project/reports",
    "/project/feedback",
    "/user/preferences", "/user/goals", "/user/constraints",
)


def context_db_root() -> Path:
    """Resolve the on-disk root at call time (so tests can set env first)."""
    override = os.environ.get("CONTEXT_DB_DIR")
    if override:
        root = Path(override)
    else:
        state = os.environ.get("STATE_DIR")
        base = Path(state) if state else Path.home() / ".ai-employee" / "state"
        root = base / "context_db"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def node_id_for(tenant: str, norm_path: str) -> str:
    """Stable node id derived from tenant + normalized path."""
    return hashlib.sha1(f"{tenant}:{norm_path}".encode("utf-8")).hexdigest()[:16]


def summarize(text: str, limit: int = _SUMMARY_CHARS) -> str:
    """Cheap L0 extract: first sentences / first *limit* chars, one line."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > limit // 3:
            return cut[: idx + 1]
    return cut.rstrip() + "…"


class ContextTree:
    """Tenant-scoped, path-safe context tree persisted as JSON node files."""

    def __init__(self, tenant: str = "default", root: Path | None = None) -> None:
        if not perms.valid_tenant(tenant):
            raise ValueError(f"invalid tenant: {tenant!r}")
        self.tenant = tenant
        self._root = Path(root) if root else context_db_root()
        self._tenant_root = (self._root / tenant).resolve()
        self._tenant_root.mkdir(parents=True, exist_ok=True)

    # ── Path plumbing ─────────────────────────────────────────────────────────

    def _disk_path(self, norm_path: str, *, is_dir: bool = False) -> Path:
        rel = norm_path.lstrip("/")
        full = (self._tenant_root / rel).resolve()
        if is_dir is False:
            full = full.with_name(full.name + _NODE_SUFFIX)
        # Containment guard — belt and braces on top of normalize_path.
        if not str(full).startswith(str(self._tenant_root) + os.sep):
            raise ValueError("path escapes tenant root")
        return full

    def _norm(self, node_path: str) -> str:
        norm = perms.normalize_path(node_path)
        if not perms.check(norm, self.tenant, None):
            raise ValueError(f"path not permitted: {node_path!r}")
        return norm

    def ensure_layout(self) -> None:
        """Create the canonical category directories (idempotent)."""
        for d in CANONICAL_LAYOUT:
            self._disk_path(d, is_dir=True).mkdir(parents=True, exist_ok=True)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def write(self, node_path: str, content: str,
              metadata: dict[str, Any] | None = None,
              validate: bool = True) -> str:
        """Write/overwrite a node; returns its stable node id.

        ``validate=True`` (default) re-checks the permission gate explicitly;
        path normalization + containment always run regardless.
        """
        norm = self._norm(node_path)
        if validate and not perms.check(norm, self.tenant, None):
            raise ValueError(f"write not permitted: {node_path!r}")
        disk = self._disk_path(norm)
        with _LOCK:
            existing = self._load_file(disk)
            node = {
                "id": node_id_for(self.tenant, norm),
                "path": norm,
                "content": str(content or ""),
                "summary": summarize(content),
                "metadata": dict(metadata or {}),
                "created_at": (existing or {}).get("created_at", _ts()),
                "updated_at": _ts(),
            }
            disk.parent.mkdir(parents=True, exist_ok=True)
            disk.write_text(json.dumps(node, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        return node["id"]

    def read(self, node_path: str) -> dict[str, Any] | None:
        """Return the full node dict, or None when absent."""
        try:
            norm = self._norm(node_path)
        except ValueError:
            return None
        with _LOCK:
            return self._load_file(self._disk_path(norm))

    def read_by_id(self, node_id: str) -> dict[str, Any] | None:
        """Linear scan lookup by stable id (trees are small; ok for now)."""
        nid = str(node_id or "").strip()
        if not nid:
            return None
        for node in self.walk_nodes("/"):
            if node.get("id") == nid:
                return node
        return None

    def list(self, dir_path: str) -> list[dict[str, Any]]:
        """Summaries of one directory level: node L0 cards + subdir markers."""
        norm = self._norm(dir_path)
        disk_dir = self._disk_path(norm, is_dir=True)
        out: list[dict[str, Any]] = []
        if not disk_dir.is_dir():
            return out
        with _LOCK:
            for entry in sorted(disk_dir.iterdir()):
                if entry.is_dir():
                    out.append({"kind": "dir",
                                "path": f"{norm}/{entry.name}",
                                "children": len(list(entry.iterdir()))})
                elif entry.suffix == _NODE_SUFFIX:
                    node = self._load_file(entry)
                    if node:
                        out.append({"kind": "node", "id": node.get("id"),
                                    "path": node.get("path"),
                                    "summary": node.get("summary", ""),
                                    "updated_at": node.get("updated_at")})
        return out

    def delete(self, node_path: str) -> bool:
        """Delete a node file. Returns True when something was removed."""
        try:
            norm = self._norm(node_path)
        except ValueError:
            return False
        disk = self._disk_path(norm)
        with _LOCK:
            if disk.is_file():
                disk.unlink()
                return True
        return False

    def move(self, src: str, dst: str) -> dict[str, Any]:
        """Move a node; id is re-derived from the new path, created_at kept."""
        src_norm = self._norm(src)
        dst_norm = self._norm(dst)
        with _LOCK:
            node = self._load_file(self._disk_path(src_norm))
            if node is None:
                raise FileNotFoundError(f"no node at {src_norm}")
            node["path"] = dst_norm
            node["id"] = node_id_for(self.tenant, dst_norm)
            node["updated_at"] = _ts()
            dst_disk = self._disk_path(dst_norm)
            dst_disk.parent.mkdir(parents=True, exist_ok=True)
            dst_disk.write_text(json.dumps(node, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            self._disk_path(src_norm).unlink()
        return node

    # ── Iteration (used by retriever/loader) ─────────────────────────────────

    def walk_nodes(self, base: str = "/",
                   max_depth: int | None = None) -> Iterator[dict[str, Any]]:
        """Yield node dicts under *base* (logical depth-limited when asked)."""
        if base in ("/", ""):
            start = self._tenant_root
            base_depth = 0
        else:
            norm = self._norm(base)
            start = self._disk_path(norm, is_dir=True)
            base_depth = len(norm.strip("/").split("/"))
        if not start.is_dir():
            return
        for dirpath, _dirnames, filenames in os.walk(start):
            for fn in sorted(filenames):
                if not fn.endswith(_NODE_SUFFIX):
                    continue
                fp = Path(dirpath) / fn
                node = self._load_file(fp)
                if not node:
                    continue
                depth = len(str(node.get("path", "")).strip("/").split("/"))
                if max_depth is not None and depth - base_depth > max_depth:
                    continue
                yield node

    def list_dirs(self, max_depth: int = 2) -> list[str]:
        """Logical paths of directories up to *max_depth* segments deep."""
        out: list[str] = []
        root = self._tenant_root
        for dirpath, dirnames, _ in os.walk(root):
            dirnames.sort()
            for d in dirnames:
                rel = (Path(dirpath) / d).relative_to(root).as_posix()
                if len(rel.split("/")) <= max_depth:
                    out.append("/" + rel)
        return out

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _load_file(disk: Path) -> dict[str, Any] | None:
        try:
            if not disk.is_file():
                return None
            data = json.loads(disk.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None
