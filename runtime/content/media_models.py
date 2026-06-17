"""Media-model catalog for content creation.

Single source of truth: the vendored Open-Generative-AI base
(``vendor/open-generative-ai/``). We merge two assets from it:
  - ``models.js``        — broad id → {name, endpoint} set (image + video, 150+)
  - ``models_dump.json`` — full input schemas for the curated image models

No model names are hardcoded here — everything is read from the vendored catalog,
so refreshing the base (re-copying those two files) updates the system.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "open-generative-ai"

# Matches a model object's id → name → endpoint when they appear in order with no
# intervening braces (true for these objects: endpoint precedes the inputs block).
# Conservative on purpose: a non-match falls back to endpoint == id, never a mispair.
_ID_NAME_ENDPOINT = re.compile(
    r'"id"\s*:\s*"([^"]+)"\s*,\s*"name"\s*:\s*"([^"]*)"\s*,\s*"endpoint"\s*:\s*"([^"]+)"')


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}

    # 1) models.js → id/name/endpoint for the broad catalog (image + video).
    try:
        js = (_VENDOR / "models.js").read_text(encoding="utf-8", errors="replace")
        for mid, name, endpoint in _ID_NAME_ENDPOINT.findall(js):
            models[mid] = {"id": mid, "name": name or mid,
                           "endpoint": endpoint or mid, "inputs": {}}
    except Exception:
        pass

    # 2) models_dump.json → overlay full input schemas (valid JSON, image models).
    try:
        dump = json.loads((_VENDOR / "models_dump.json").read_text(encoding="utf-8"))
        for group in dump.values():
            if not isinstance(group, list):
                continue
            for m in group:
                mid = m.get("id")
                if not mid:
                    continue
                entry = models.setdefault(
                    mid, {"id": mid, "name": m.get("name") or mid,
                          "endpoint": m.get("endpoint") or mid, "inputs": {}})
                if m.get("inputs"):
                    entry["inputs"] = m["inputs"]
                if m.get("name"):
                    entry["name"] = m["name"]
                if m.get("endpoint"):
                    entry["endpoint"] = m["endpoint"]
    except Exception:
        pass

    return models


def list_models() -> list[dict[str, Any]]:
    """All known media models (id, name, endpoint, inputs), id-sorted."""
    return sorted(_catalog().values(), key=lambda m: m["id"])


def get_model(model_id: str) -> dict[str, Any] | None:
    return _catalog().get(model_id)


def endpoint_for(model_id: str) -> str:
    """MuAPI endpoint path for a model id (falls back to the id itself)."""
    return (_catalog().get(model_id) or {}).get("endpoint") or model_id


def count() -> int:
    return len(_catalog())


# ── Local / offline catalog (stable-diffusion.cpp via sd-cli) ─────────────────
# The DEFAULT content-creation path is local + offline. The cloud catalog above
# (MuAPI) is opt-in. Local models run fully on-device on an 8GB GPU.

@lru_cache(maxsize=1)
def _local() -> dict[str, Any]:
    try:
        return json.loads((_VENDOR / "local_models.json").read_text(encoding="utf-8"))
    except Exception:
        return {"models": [], "auxiliary": {}, "_meta": {}}


def local_models() -> list[dict[str, Any]]:
    """Installed-or-installable local image models (sd-cli). provider='sdcpp'."""
    return [{**m, "provider": "sdcpp"} for m in (_local().get("models") or [])]


def get_local_model(model_id: str) -> dict[str, Any] | None:
    for m in local_models():
        if m["id"] == model_id:
            return m
    return None


def default_local_model_id() -> str:
    return os.getenv("SD_DEFAULT_MODEL") or _local().get("_meta", {}).get(
        "default_model") or "dreamshaper-8"


def zimage_aux() -> dict[str, Any]:
    """Shared llm + vae files required by z-image models."""
    return _local().get("auxiliary") or {}
