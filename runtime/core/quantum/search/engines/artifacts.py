from __future__ import annotations
import asyncio
import hashlib
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_ARTIFACTS_DIR = os.path.join(_REPO_ROOT, 'state', 'artifacts')


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


class ArtifactEngine:
    name = 'artifacts'
    source_type = 'ui_component'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('ArtifactEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        artifact_dicts = self._load_artifacts(request)
        results: list[NormalizedSearchResult] = []

        for art in artifact_dicts:
            name = art.get('name', art.get('id', ''))
            art_type = art.get('type', '')
            content = f"{name} {art_type} {art.get('path', '')} {art.get('source', '')}"
            score = _keyword_score(tokens, content)
            if score == 0.0:
                continue
            # Short non-security UID for an artifact (id/name) — not a credential.
            uid = hashlib.md5(f"artifact:{art.get('id', name)}".encode(), usedforsecurity=False).hexdigest()[:12]
            results.append(NormalizedSearchResult(
                id=uid,
                title=name,
                content=content[:500],
                url=art.get('path', art.get('url', 'state/artifacts/')),
                source_type='ui_component',
                engine=self.name,
                score=score,
                metadata={k: art[k] for k in ('type', 'version', 'created_at') if k in art},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]

    def _load_artifacts(self, request: SearchRequest) -> list[dict]:
        # Try live artifact_manager first
        try:
            import sys
            sys.path.insert(0, os.path.join(_REPO_ROOT, 'runtime'))
            from core.artifact_manager import list_artifacts  # type: ignore
            arts = list_artifacts(limit=request.max_results_per_engine * 2)
            if request.tenant_id:
                arts = [a for a in arts if a.get('tenant_id', '') in ('', request.tenant_id)]
            return arts
        except Exception as exc:
            log.debug('artifact_manager import failed: %s', exc)

        # Fallback: scan state/artifacts/ directory
        if not os.path.isdir(_ARTIFACTS_DIR):
            return []

        artifacts = []
        for fname in os.listdir(_ARTIFACTS_DIR):
            fpath = os.path.join(_ARTIFACTS_DIR, fname)
            artifacts.append({
                'id': fname,
                'name': fname,
                'path': os.path.relpath(fpath, _REPO_ROOT),
                'type': os.path.splitext(fname)[1].lstrip('.') or 'unknown',
            })
        return artifacts
