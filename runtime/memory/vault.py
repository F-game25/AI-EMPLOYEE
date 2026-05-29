"""
Vault — Obsidian-compatible markdown knowledge store for AI-EMPLOYEE.

Notes live as .md files with YAML frontmatter under ~/.ai-employee/vault/.
Real Obsidian can open the same folder. Backlinks + indices are derived from
[[wikilinks]] embedded in note bodies.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional, Tuple, Dict

import frontmatter  # python-frontmatter

from .wikilink_resolver import (
    extract_wikilinks,
    build_backlinks_index,
    find_broken_links,
    title_to_id,
)

FOLDERS = ("concepts", "people", "projects", "topics", "daily")
TRASH = "_trash"


@dataclass
class NoteRef:
    id: str
    title: str
    folder: str
    path: str
    tags: List[str] = field(default_factory=list)
    updated: float = 0.0


@dataclass
class Note:
    id: str
    title: str
    folder: str
    path: str
    frontmatter: dict
    body: str
    wikilinks: List[str] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)
    created: float = 0.0
    updated: float = 0.0


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_frontmatter(note_id: str, title: str) -> dict:
    return {
        "id": note_id,
        "title": title,
        "created": _now_iso(),
        "updated": _now_iso(),
        "tags": [],
        "sources": [],
        "confidence": 0.5,
        "verified_by": "user",
        "skill_level": 0.0,
        "importance": 0.5,
    }


class Vault:
    LEGACY_ROOT = Path(os.path.expanduser("~/.ai-employee/vault"))

    def __init__(self, tenant_id: str = "default", root: Optional[str] = None):
        # Per-tenant namespacing (2026-05-18 security audit CRITICAL #2):
        # each tenant gets its own vault folder. Notes never cross tenant boundaries.
        self.tenant_id = tenant_id
        if root is None:
            root = f"~/.ai-employee/tenants/{tenant_id}/vault"
        self.root = Path(os.path.expanduser(root)).resolve()
        # One-shot migration: if legacy vault exists with content AND we are the
        # 'default' tenant AND our tenant vault is empty (no .md files), copy
        # the notes over. We use COPY (not move) so the operator can verify
        # the migration before manually removing the legacy directory.
        if tenant_id == "default" and self.LEGACY_ROOT.exists():
            legacy_md = list(self.LEGACY_ROOT.rglob("*.md"))
            tenant_md = list(self.root.rglob("*.md")) if self.root.exists() else []
            if legacy_md and not tenant_md:
                import shutil
                self.root.mkdir(parents=True, exist_ok=True)
                for src in self.LEGACY_ROOT.iterdir():
                    dst = self.root / src.name
                    if dst.exists():
                        continue
                    if src.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                # Mark legacy as migrated (don't delete — operator can review)
                (self.LEGACY_ROOT / ".MIGRATED_TO_TENANT").write_text(
                    f"Notes copied to {self.root}\nSafe to delete after verification.\n"
                )
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_scaffolding()
        self._index_cache: Optional[dict] = None
        self._backlinks_cache: Optional[dict] = None

    # -- scaffolding ---------------------------------------------------------
    def _ensure_scaffolding(self) -> None:
        for folder in (*FOLDERS, TRASH):
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    # -- internal helpers ----------------------------------------------------
    def _all_md_files(self) -> List[Path]:
        return [
            p for p in self.root.rglob("*.md")
            if TRASH not in p.parts
        ]

    def _resolve_path(self, note_id: str) -> Optional[Path]:
        """Find the .md file whose frontmatter.id matches note_id."""
        for p in self._all_md_files():
            try:
                post = frontmatter.load(p)
                if post.metadata.get("id") == note_id:
                    return p
            except Exception:
                continue
        # Fallback: filename-based match
        for p in self._all_md_files():
            if p.stem.lower() == note_id.lower():
                return p
        return None

    def _unique_filename(self, folder: Path, base_id: str) -> Path:
        candidate = folder / f"{base_id}.md"
        if not candidate.exists():
            return candidate
        i = 2
        while True:
            c = folder / f"{base_id}-{i}.md"
            if not c.exists():
                return c
            i += 1

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            dir=str(path.parent), prefix=".tmp_", suffix=".md",
        )
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(tmp.name, path)
        except Exception:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            raise

    def _post_to_note(self, post: frontmatter.Post, path: Path) -> Note:
        rel = path.relative_to(self.root)
        folder = rel.parts[0] if len(rel.parts) > 1 else ""
        meta = dict(post.metadata or {})
        note_id = meta.get("id") or path.stem.lower()
        title = meta.get("title") or path.stem.replace("-", " ").title()
        body = post.content or ""
        wl = extract_wikilinks(body)
        st = path.stat()
        return Note(
            id=note_id,
            title=title,
            folder=folder,
            path=str(path),
            frontmatter=meta,
            body=body,
            wikilinks=wl,
            backlinks=self.get_backlinks(note_id),
            created=meta.get("_created_ts", st.st_ctime),
            updated=st.st_mtime,
        )

    # -- public API ----------------------------------------------------------
    def list_notes(self, folder: Optional[str] = None, tag: Optional[str] = None) -> List[NoteRef]:
        results: List[NoteRef] = []
        for p in self._all_md_files():
            rel = p.relative_to(self.root)
            f = rel.parts[0] if len(rel.parts) > 1 else ""
            if folder and f != folder:
                continue
            try:
                post = frontmatter.load(p)
            except Exception:
                continue
            meta = post.metadata or {}
            tags = meta.get("tags") or []
            if tag and tag not in tags:
                continue
            results.append(NoteRef(
                id=meta.get("id") or p.stem.lower(),
                title=meta.get("title") or p.stem.replace("-", " ").title(),
                folder=f,
                path=str(p),
                tags=list(tags),
                updated=p.stat().st_mtime,
            ))
        return sorted(results, key=lambda r: r.updated, reverse=True)

    def get_note(self, id: str) -> Optional[Note]:
        path = self._resolve_path(id)
        if not path:
            return None
        try:
            post = frontmatter.load(path)
        except Exception:
            return None
        return self._post_to_note(post, path)

    def write_note(self, id: str, body: str, frontmatter_data: Optional[dict] = None) -> Note:
        frontmatter_data = frontmatter_data or {}
        path = self._resolve_path(id)
        if not path:
            # create in concepts/ as fallback
            title = frontmatter_data.get("title") or id.replace("-", " ").title()
            return self.create_note(title, folder="concepts", body=body, frontmatter=frontmatter_data)
        meta = _default_frontmatter(id, frontmatter_data.get("title", id))
        # preserve original created if present
        try:
            existing = frontmatter.load(path).metadata or {}
            if existing.get("created"):
                meta["created"] = existing["created"]
        except Exception:
            pass
        meta.update(frontmatter_data or {})
        meta["id"] = id
        meta["updated"] = _now_iso()
        post = frontmatter.Post(body, **meta)
        self._atomic_write(path, frontmatter.dumps(post))
        return self._post_to_note(post, path)

    def create_note(self, title: str, folder: str = "concepts", body: str = "",
                    frontmatter: Optional[dict] = None) -> Note:
        if folder not in FOLDERS:
            folder = "concepts"
        folder_path = self.root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        note_id = title_to_id(title)
        file_path = self._unique_filename(folder_path, note_id)
        # if filename was renamed for uniqueness, adapt id
        final_id = file_path.stem
        meta = _default_frontmatter(final_id, title)
        if frontmatter:
            meta.update(frontmatter)
        meta["id"] = final_id
        meta["title"] = title
        import frontmatter as _fm  # local alias to avoid shadowing
        post = _fm.Post(body, **meta)
        self._atomic_write(file_path, _fm.dumps(post))
        return self._post_to_note(post, file_path)

    def delete_note(self, id: str) -> bool:
        path = self._resolve_path(id)
        if not path:
            return False
        dest_dir = self.root / TRASH
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{int(time.time())}_{path.name}"
        shutil.move(str(path), str(dest))
        return True

    def search(self, query: str, top_k: int = 20) -> List[NoteRef]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: List[Tuple[int, NoteRef]] = []
        for ref in self.list_notes():
            try:
                text = Path(ref.path).read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            score = text.count(q)
            if ref.title.lower().find(q) >= 0:
                score += 5
            if score > 0:
                hits.append((score, ref))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in hits[:top_k]]

    def rebuild_indices(self) -> dict:
        backlinks = build_backlinks_index(self)
        index = []
        for ref in self.list_notes():
            index.append(asdict(ref))
        bpath = self.root / "_backlinks.json"
        ipath = self.root / "_index.json"
        self._atomic_write(bpath, json.dumps(backlinks, indent=2))
        self._atomic_write(ipath, json.dumps(index, indent=2))
        self._backlinks_cache = backlinks
        self._index_cache = index
        broken = find_broken_links(self)
        return {
            "note_count": len(index),
            "backlink_count": sum(len(v) for v in backlinks.values()),
            "broken_link_count": len(broken),
        }

    def get_backlinks(self, note_id: str) -> List[str]:
        if self._backlinks_cache is None:
            bpath = self.root / "_backlinks.json"
            if bpath.exists():
                try:
                    self._backlinks_cache = json.loads(bpath.read_text(encoding="utf-8"))
                except Exception:
                    self._backlinks_cache = {}
            else:
                self._backlinks_cache = {}
        return list(self._backlinks_cache.get(note_id, []))

    def get_broken_links(self) -> List[Tuple[str, str]]:
        return find_broken_links(self)

    def export_path(self) -> str:
        return str(self.root)


# ── Per-tenant cached vault instances ──────────────────────────────────────
_tenant_vaults: dict = {}


def _current_tenant_id() -> str:
    """Resolve active tenant from request context; fall back to 'default'."""
    try:
        from core.tenancy import _current_tenant  # ContextVar
        ctx = _current_tenant.get()
        if ctx and ctx.tenant_id:
            return ctx.tenant_id
    except Exception:
        pass
    return "default"


def get_vault(tenant_id: Optional[str] = None) -> "Vault":
    """Return the Vault instance for the active tenant (cached per tenant)."""
    tid = tenant_id or _current_tenant_id()
    if tid not in _tenant_vaults:
        _tenant_vaults[tid] = Vault(tenant_id=tid)
    return _tenant_vaults[tid]
