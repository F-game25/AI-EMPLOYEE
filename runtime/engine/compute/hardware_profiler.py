"""Hardware profiler — live, measured machine state for model selection.

Single source of truth for "what can this box actually run *right now*". Every
function returns a **measured** value (or ``None`` when the probe is unavailable)
and **never raises** — selection logic must degrade gracefully, not crash, when
``nvidia-smi`` or Ollama are absent.

Probes
------
  live_vram_mb()      free GPU VRAM in MB         (nvidia-smi --query-gpu=memory.free)
  total_vram_mb()     total GPU VRAM in MB        (nvidia-smi --query-gpu=memory.total)
  ram_available_mb()  available system RAM in MB  (psutil, /proc/meminfo fallback)
  cpu_threads()       logical CPU count
  ollama_inventory()  installed Ollama models     (GET /api/tags)
  ollama_loaded()     resident models + CPU/GPU split (GET /api/ps)

This centralizes the ad-hoc ``_free_vram_mb()`` that lived in
``neural_brain/models/lifecycle_manager.py`` — that module now delegates here.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Ollama HTTP host — env-overridable, no hardcoded literal in callers.
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_NVIDIA_SMI_TIMEOUT_S = 4
_OLLAMA_TIMEOUT_S = 4


def _nvidia_query(field: str) -> int | None:
    """Run ``nvidia-smi --query-gpu=<field> --format=csv,noheader,nounits``.

    Returns the first GPU's value in MB, or ``None`` if nvidia-smi is missing,
    times out, or returns nothing parseable. Never raises.
    """
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
            text=True, timeout=_NVIDIA_SMI_TIMEOUT_S)
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return int(lines[0]) if lines else None
    except Exception as exc:  # noqa: BLE001 — probe must never break callers
        logger.debug("hardware_profiler: nvidia-smi %s failed: %s", field, exc)
        return None


def live_vram_mb() -> int | None:
    """Free GPU VRAM in MB *right now*, or ``None`` on a GPU-less / no-driver host."""
    return _nvidia_query("memory.free")


def total_vram_mb() -> int | None:
    """Total GPU VRAM in MB, or ``None`` on a GPU-less / no-driver host."""
    return _nvidia_query("memory.total")


def ram_available_mb() -> int | None:
    """Available system RAM in MB. Prefers psutil; falls back to /proc/meminfo."""
    try:
        import psutil
        return int(psutil.virtual_memory().available / (1024 * 1024))
    except Exception as exc:  # noqa: BLE001
        logger.debug("hardware_profiler: psutil unavailable (%s); trying /proc/meminfo", exc)
    try:
        with open("/proc/meminfo", "r") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(int(line.split()[1]) / 1024)  # kB → MB
    except Exception as exc:  # noqa: BLE001
        logger.debug("hardware_profiler: /proc/meminfo read failed: %s", exc)
    return None


def cpu_threads() -> int | None:
    """Number of logical CPU threads, or ``None`` if undetectable."""
    try:
        return os.cpu_count()
    except Exception as exc:  # noqa: BLE001
        logger.debug("hardware_profiler: cpu_count failed: %s", exc)
        return None


def _ollama_get(path: str) -> dict | None:
    """GET a JSON endpoint on the Ollama HTTP API. Returns dict or ``None``."""
    url = f"{_OLLAMA_HOST}{path}"
    # Prefer requests; fall back to stdlib so this has no hard third-party dep.
    try:
        import requests
        resp = requests.get(url, timeout=_OLLAMA_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("hardware_profiler: requests GET %s failed (%s); trying urllib", path, exc)
    try:
        import json as _json
        from urllib.request import urlopen
        with urlopen(url, timeout=_OLLAMA_TIMEOUT_S) as fh:
            return _json.loads(fh.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("hardware_profiler: urllib GET %s failed: %s", path, exc)
        return None


def ollama_inventory() -> list[dict] | None:
    """Installed Ollama models via ``GET /api/tags``.

    Returns a list of ``{name, size_mb, family, parameter_size, quantization}``
    dicts, or ``None`` if Ollama is unreachable. Empty list = reachable, no models.
    """
    data = _ollama_get("/api/tags")
    if data is None:
        return None
    out: list[dict] = []
    for m in data.get("models", []) or []:
        details = m.get("details", {}) or {}
        out.append({
            "name": m.get("name"),
            "size_mb": int((m.get("size") or 0) / (1024 * 1024)),
            "family": details.get("family"),
            "parameter_size": details.get("parameter_size"),
            "quantization": details.get("quantization_level"),
        })
    return out


def ollama_loaded() -> list[dict] | None:
    """Currently resident Ollama models via ``GET /api/ps``, incl. CPU/GPU split.

    Ollama reports total ``size`` and the GPU-resident ``size_vram``; the remainder
    spilled to CPU/RAM is ``size - size_vram``. Returns a list of
    ``{name, size_mb, vram_mb, cpu_mb, gpu_fraction, context_length}`` dicts, or
    ``None`` if Ollama is unreachable. Empty list = reachable, nothing loaded.
    """
    data = _ollama_get("/api/ps")
    if data is None:
        return None
    out: list[dict] = []
    for m in data.get("models", []) or []:
        size = int(m.get("size") or 0)
        vram = int(m.get("size_vram") or 0)
        cpu = max(size - vram, 0)
        out.append({
            "name": m.get("name"),
            "size_mb": int(size / (1024 * 1024)),
            "vram_mb": int(vram / (1024 * 1024)),
            "cpu_mb": int(cpu / (1024 * 1024)),
            "gpu_fraction": round(vram / size, 3) if size else None,
            "context_length": m.get("context_length"),
        })
    return out


def snapshot() -> dict:
    """One-shot measured profile of the box — for diagnostics / the Models UI."""
    return {
        "vram_free_mb": live_vram_mb(),
        "vram_total_mb": total_vram_mb(),
        "ram_available_mb": ram_available_mb(),
        "cpu_threads": cpu_threads(),
        "ollama_models": ollama_inventory(),
        "ollama_loaded": ollama_loaded(),
    }
