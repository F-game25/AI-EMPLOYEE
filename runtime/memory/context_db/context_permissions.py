"""Fail-closed permission checks for the context database.

``check(path, tenant, allowed_scopes)`` is the single authority used by the
tree (writes) and the retriever (reads). Any malformed input, traversal
attempt, bad tenant or scope miss returns ``False`` — never raises, never
defaults open.

Scope semantics (turbovec allowlist pattern):
  - ``allowed_scopes=None``  → caller imposes no scope restriction
                               (tenant + path-shape checks still apply).
  - ``allowed_scopes=[...]`` → path must live under one of the scope
                               prefixes (e.g. ``"/project/goals"``).
  - ``allowed_scopes=[]``    → deny everything (explicit empty allowlist).
"""
from __future__ import annotations

import posixpath
import re

ALLOWED_ROOTS = ("project", "user")
_TENANT_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_\-. ]{1,128}$")


def normalize_path(path: str) -> str:
    """Normalize a logical node path; raise ``ValueError`` on anything unsafe.

    Returns a canonical ``/root/seg/...`` path whose first segment is in
    ``ALLOWED_ROOTS``. Rejects traversal (``..``), empty/dot segments and
    characters outside a conservative allowlist.
    """
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("empty path")
    norm = posixpath.normpath("/" + raw.strip("/"))
    if norm in ("/", "//"):
        raise ValueError("path resolves to root")
    segments = norm.strip("/").split("/")
    for seg in segments:
        if seg in ("", ".", "..") or not _SEGMENT_RE.match(seg):
            raise ValueError(f"unsafe path segment: {seg!r}")
    if segments[0] not in ALLOWED_ROOTS:
        raise ValueError(
            f"path root must be one of {ALLOWED_ROOTS}, got {segments[0]!r}")
    return "/" + "/".join(segments)


def valid_tenant(tenant: str) -> bool:
    return bool(_TENANT_RE.match(str(tenant or "")))


def check(path: str, tenant: str = "default",
          allowed_scopes: list[str] | None = None) -> bool:
    """Return True only when *path* is safe for *tenant* under the allowlist.

    Fail closed: every error path returns False.
    """
    try:
        if not valid_tenant(tenant):
            return False
        norm = normalize_path(path)
        if allowed_scopes is None:
            return True
        scopes: list[str] = []
        for scope in allowed_scopes:
            try:
                scopes.append(normalize_path(scope))
            except ValueError:
                continue  # malformed scope grants nothing
        return any(norm == s or norm.startswith(s + "/") for s in scopes)
    except Exception:
        return False
