"""
Wikilink resolver — extract and resolve Obsidian-style [[wikilinks]].

A wikilink target can be:
  [[Page Title]]           → resolves by title
  [[Page Title|alias]]     → resolves to "Page Title", display = "alias"
  [[note-id]]              → resolves directly if id matches

Resolution is case-insensitive on the title or filename stem.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple, TYPE_CHECKING, Dict

import frontmatter

if TYPE_CHECKING:
    from .vault import Vault

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def title_to_id(title: str) -> str:
    """kebab-case the title, lowercase, ascii-fold, strip extras."""
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def extract_wikilinks(body: str) -> List[str]:
    """Return list of unique [[targets]] (group 1, not alias)."""
    if not body:
        return []
    seen: Dict[str, None] = {}
    for m in WIKILINK_RE.finditer(body):
        tgt = (m.group(1) or "").strip()
        if tgt and tgt not in seen:
            seen[tgt] = None
    return list(seen.keys())


def _build_title_id_map(vault: "Vault") -> Dict[str, str]:
    """Map lowercased title AND id → canonical note_id, for fuzzy resolution."""
    mapping: Dict[str, str] = {}
    for ref in vault.list_notes():
        mapping[ref.title.lower()] = ref.id
        mapping[ref.id.lower()] = ref.id
        # Also map filename stem
        try:
            mapping[Path(ref.path).stem.lower()] = ref.id
        except Exception:
            pass
    return mapping


def resolve(target: str, vault: "Vault", _cache: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Resolve [[target]] string → note_id. Case-insensitive."""
    if not target:
        return None
    key = target.strip().lower()
    mapping = _cache if _cache is not None else _build_title_id_map(vault)
    if key in mapping:
        return mapping[key]
    # try kebab-cased lookup
    kid = title_to_id(target)
    if kid in mapping:
        return mapping[kid]
    return None


def build_backlinks_index(vault: "Vault") -> dict:
    """Walk all notes, return { note_id: [other_note_ids that link to it] }."""
    mapping = _build_title_id_map(vault)
    backlinks: Dict[str, List[str]] = {}
    for ref in vault.list_notes():
        try:
            post = frontmatter.load(ref.path)
        except Exception:
            continue
        for tgt in extract_wikilinks(post.content or ""):
            resolved = resolve(tgt, vault, _cache=mapping)
            if not resolved or resolved == ref.id:
                continue
            backlinks.setdefault(resolved, [])
            if ref.id not in backlinks[resolved]:
                backlinks[resolved].append(ref.id)
    return backlinks


def find_broken_links(vault: "Vault") -> List[Tuple[str, str]]:
    """Return list of (source_note_id, broken_target_string)."""
    mapping = _build_title_id_map(vault)
    broken: List[Tuple[str, str]] = []
    for ref in vault.list_notes():
        try:
            post = frontmatter.load(ref.path)
        except Exception:
            continue
        for tgt in extract_wikilinks(post.content or ""):
            if resolve(tgt, vault, _cache=mapping) is None:
                broken.append((ref.id, tgt))
    return broken
