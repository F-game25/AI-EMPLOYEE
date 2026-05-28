"""KnowledgeVault — persistent, self-organizing knowledge store.

Format: Obsidian-compatible markdown files in ~/.ai-employee/vault/
- Each topic = one .md file with YAML frontmatter
- [[wikilinks]] for cross-references
- Backlink index maintained in vault/_index.json
- Confidence scores and verification status tracked
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SLUG_RE = re.compile(r'[^\w\-]')

_DEFAULT_VAULT = os.path.join(os.path.expanduser('~'), '.ai-employee', 'vault')

STATUS_PENDING  = 'pending_review'
STATUS_VERIFIED = 'verified'
STATUS_REJECTED = 'rejected'


def _slug(title: str) -> str:
    return _SLUG_RE.sub('-', title.lower().strip()).strip('-')[:120]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_wikilinks(content: str) -> list[str]:
    links: list[str] = []
    pos = 0
    while True:
        start = content.find('[[', pos)
        if start < 0:
            return links
        end = content.find(']]', start + 2)
        if end < 0:
            return links
        target = content[start + 2:end].strip()
        if target:
            links.append(target)
        pos = end + 2


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Return (meta, body) from raw markdown with optional YAML frontmatter."""
    if not raw.startswith('---'):
        return {}, raw
    end = raw.find('\n---', 3)
    if end < 0:
        return {}, raw
    fm_text = raw[3:end].strip()
    body = raw[end + 4:].lstrip('\n')
    meta: dict = {}
    for line in fm_text.splitlines():
        if ':' not in line:
            continue
        k, _, v = line.partition(':')
        k = k.strip()
        v = v.strip()
        if v.startswith('[') and v.endswith(']'):
            meta[k] = [x.strip().strip('"\'') for x in v[1:-1].split(',') if x.strip()]
        else:
            try:
                meta[k] = float(v) if '.' in v else int(v)
            except ValueError:
                meta[k] = v
    return meta, body


def _render_frontmatter(meta: dict) -> str:
    lines = ['---']
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f'{k}: [{", ".join(str(x) for x in v)}]')
        else:
            lines.append(f'{k}: {v}')
    lines.append('---')
    return '\n'.join(lines) + '\n'


class KnowledgeVault:
    def __init__(self, vault_dir: str = None):
        self._vault = Path(vault_dir or _DEFAULT_VAULT)
        self._index_path = self._vault / '_index.json'
        self._vault.mkdir(parents=True, exist_ok=True)

    # ── index helpers ──────────────────────────────────────────────────────────

    def _load_index(self) -> dict:
        return _read_json(self._index_path, {'entries': {}, 'backlinks': {}})

    def _save_index(self, idx: dict) -> None:
        _write_json(self._index_path, idx)

    def _entry_path(self, slug: str) -> Path:
        return self._vault / f'{slug}.md'

    # ── public API ─────────────────────────────────────────────────────────────

    def add_entry(self, title: str, content: str, source: str,
                  confidence: float = 0.7, tags: list = None) -> str:
        slug = _slug(title)
        path = self._entry_path(slug)
        now = _now_iso()

        # Merge with existing if present
        existing_meta = {}
        if path.exists():
            existing_meta, _ = _parse_frontmatter(path.read_text(encoding='utf-8'))

        meta = {
            'title': title,
            'source': source,
            'confidence': round(float(confidence), 3),
            'status': existing_meta.get('status', STATUS_PENDING),
            'created': existing_meta.get('created', now),
            'updated': now,
            'tags': tags or existing_meta.get('tags', []),
        }

        wikilinks = _extract_wikilinks(content)
        raw = _render_frontmatter(meta) + f'\n{content}\n'
        path.write_text(raw, encoding='utf-8')

        # Update index
        idx = self._load_index()
        idx['entries'][slug] = {
            'title': title, 'slug': slug,
            'confidence': meta['confidence'],
            'status': meta['status'],
            'tags': meta['tags'],
            'created': meta['created'],
            'updated': now,
            'wikilinks': wikilinks,
        }
        # Update backlinks: for each [[target]], record slug as a backlink source
        for target_title in wikilinks:
            target_slug = _slug(target_title)
            bl = idx['backlinks'].setdefault(target_slug, [])
            if slug not in bl:
                bl.append(slug)
        self._save_index(idx)
        return slug

    def get_entry(self, title: str) -> dict:
        slug = _slug(title)
        path = self._entry_path(slug)
        if not path.exists():
            return {}
        raw = path.read_text(encoding='utf-8')
        meta, body = _parse_frontmatter(raw)
        idx = self._load_index()
        return {
            'slug': slug,
            'title': meta.get('title', title),
            'content': body,
            'source': meta.get('source', ''),
            'confidence': meta.get('confidence', 0.7),
            'status': meta.get('status', STATUS_PENDING),
            'created': meta.get('created', ''),
            'updated': meta.get('updated', ''),
            'tags': meta.get('tags', []),
            'backlinks': idx.get('backlinks', {}).get(slug, []),
            'wikilinks': idx.get('entries', {}).get(slug, {}).get('wikilinks', []),
        }

    def search(self, query: str, limit: int = 10) -> list:
        q = query.lower()
        results = []
        idx = self._load_index()
        for slug, info in idx.get('entries', {}).items():
            score = 0
            title_l = info.get('title', '').lower()
            if q in title_l:
                score += 2
            tags_l = ' '.join(info.get('tags', [])).lower()
            if q in tags_l:
                score += 1
            # Full-text check in file
            path = self._entry_path(slug)
            if path.exists():
                try:
                    body_l = path.read_text(encoding='utf-8').lower()
                    if q in body_l:
                        score += 1
                except Exception:
                    pass
            if score:
                results.append({**info, 'slug': slug, '_score': score})
        results.sort(key=lambda x: (-x['_score'], x.get('updated', '')), reverse=False)
        results.sort(key=lambda x: -x['_score'])
        return results[:limit]

    def get_backlinks(self, title: str) -> list:
        slug = _slug(title)
        idx = self._load_index()
        return idx.get('backlinks', {}).get(slug, [])

    def update_confidence(self, title: str, delta: float) -> None:
        slug = _slug(title)
        path = self._entry_path(slug)
        if not path.exists():
            return
        raw = path.read_text(encoding='utf-8')
        meta, body = _parse_frontmatter(raw)
        meta['confidence'] = round(min(1.0, max(0.0, float(meta.get('confidence', 0.7)) + delta)), 3)
        meta['updated'] = _now_iso()
        path.write_text(_render_frontmatter(meta) + f'\n{body}\n', encoding='utf-8')
        # Sync index
        idx = self._load_index()
        if slug in idx.get('entries', {}):
            idx['entries'][slug]['confidence'] = meta['confidence']
            idx['entries'][slug]['updated'] = meta['updated']
            self._save_index(idx)

    def list_pending_review(self) -> list:
        idx = self._load_index()
        return [
            info for info in idx.get('entries', {}).values()
            if info.get('status') == STATUS_PENDING
        ]

    def list_all(self) -> list:
        idx = self._load_index()
        return list(idx.get('entries', {}).values())

    def mark_verified(self, title: str) -> None:
        self._set_status(title, STATUS_VERIFIED)

    def mark_rejected(self, title: str) -> None:
        self._set_status(title, STATUS_REJECTED)

    def _set_status(self, title: str, status: str) -> None:
        slug = _slug(title)
        path = self._entry_path(slug)
        if not path.exists():
            return
        raw = path.read_text(encoding='utf-8')
        meta, body = _parse_frontmatter(raw)
        meta['status'] = status
        meta['updated'] = _now_iso()
        path.write_text(_render_frontmatter(meta) + f'\n{body}\n', encoding='utf-8')
        idx = self._load_index()
        if slug in idx.get('entries', {}):
            idx['entries'][slug]['status'] = status
            idx['entries'][slug]['updated'] = meta['updated']
            self._save_index(idx)

    def export_context(self, titles: list) -> str:
        """Export entries as LLM-ready context with citations."""
        parts = []
        for title in titles:
            entry = self.get_entry(title)
            if not entry:
                continue
            conf = entry.get('confidence', 0)
            status = entry.get('status', '')
            source = entry.get('source', 'unknown')
            content = entry.get('content', '').strip()
            parts.append(
                f"## {entry.get('title', title)}\n"
                f"> Source: {source} | Confidence: {conf:.0%} | Status: {status}\n\n"
                f"{content}"
            )
        return '\n\n---\n\n'.join(parts)

    def prune_low_confidence(self, threshold: float = 0.3, older_than_days: int = 7) -> int:
        """Delete entries with confidence below threshold that are older than N days."""
        cutoff = time.time() - older_than_days * 86400
        idx = self._load_index()
        removed = 0
        for slug, info in list(idx.get('entries', {}).items()):
            if info.get('confidence', 1.0) >= threshold:
                continue
            try:
                updated_ts = datetime.fromisoformat(info.get('updated', '')).timestamp()
            except Exception:
                continue
            if updated_ts > cutoff:
                continue
            path = self._entry_path(slug)
            if path.exists():
                path.unlink()
            del idx['entries'][slug]
            removed += 1
        if removed:
            self._save_index(idx)
        return removed


# Singleton accessor
_vault_instance: Optional[KnowledgeVault] = None


def get_knowledge_vault(vault_dir: str = None) -> KnowledgeVault:
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = KnowledgeVault(vault_dir)
    return _vault_instance
