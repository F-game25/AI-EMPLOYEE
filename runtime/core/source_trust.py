"""Per-source trust weighting for research findings.

Maps a URL/domain to a trust weight in [0, 1] using a tiered, regex-based
config. Weight is used as the ``importance`` parameter when persisting a
research finding into the memory router, so high-trust sources are
retained longer and ranked higher in retrieval.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "source_trust.json"
_LOCK = threading.Lock()
_CACHE: Optional[dict] = None
_COMPILED: list[tuple[float, list[re.Pattern]]] = []


def _load() -> dict:
    global _CACHE, _COMPILED
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("source_trust: failed to load %s (%s); using empty config", _CONFIG_PATH, e)
            data = {"tiers": [], "default_weight": 0.4}
        compiled: list[tuple[float, list[re.Pattern]]] = []
        for tier in data.get("tiers", []):
            try:
                w = float(tier.get("weight", 0.4))
                patterns = [re.compile(p, re.IGNORECASE) for p in tier.get("patterns", [])]
                compiled.append((w, patterns))
            except re.error as e:
                logger.warning("source_trust: bad pattern in tier weight=%s: %s", tier.get("weight"), e)
        _CACHE = data
        _COMPILED = compiled
        return data


def trust_for_url(url: str) -> float:
    """Return trust weight in [0, 1] for the given URL.

    Falls back to ``default_weight`` if no tier matches. Best-effort: malformed
    URLs return the default weight rather than raising.
    """
    cfg = _load()
    if not url:
        return float(cfg.get("default_weight", 0.4))
    try:
        host = (urlparse(url).hostname or "").lower()
        target = f"{host}{urlparse(url).path or ''}"
    except Exception:
        return float(cfg.get("default_weight", 0.4))
    for weight, patterns in _COMPILED:
        for p in patterns:
            if p.search(target):
                return weight
    return float(cfg.get("default_weight", 0.4))


def trust_for_urls(urls: Iterable[str]) -> dict[str, float]:
    """Batch helper — returns ``{url: weight}``."""
    return {u: trust_for_url(u) for u in urls}


def reload() -> None:
    """Reload config from disk (test/admin hook)."""
    global _CACHE, _COMPILED
    with _LOCK:
        _CACHE = None
        _COMPILED = []
    _load()
