"""Hardware-aware model resolver.

The static model_registry.json lists *preferred* models per architecture, but those
models may not be installed on this machine, and a fixed choice ignores the host's
specs. This resolver inspects what is actually installed in Ollama and the host
hardware tier, then maps each of the 8 architectures to the best *runnable* model.

This is what makes the local AI "interchangeable depending on system specs" instead
of one hardcoded model: a low-end CPU box gets small fast models, a GPU box gets the
larger capable ones — automatically, from whatever the user has pulled.

Pure stdlib + optional psutil. Never raises — always returns a usable mapping.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.request

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

# Per-architecture preference ladders (best→smallest). First *installed* match wins,
# filtered by what the hardware tier can comfortably run. Names are matched as
# prefixes against installed tags (e.g. "llama3.1" matches "llama3.1:latest").
_ARCH_PREFS: dict[str, list[str]] = {
    # General reasoning / planning / coding / deep analysis
    "LLM":  ["qwen2.5-coder:14b", "qwen3.5", "llama3.1", "qwen2.5:7b", "llama3", "llama3.2", "gemma3"],
    # Fast, cheap, short tasks / classification — smallest capable model
    "SLM":  ["llama3.2", "qwen2.5:1.5b", "qwen2.5:3b", "gemma3", "phi3", "llama3.1"],
    # Mixture-of-experts style model (rare locally) — fall back to a strong dense model
    "MoE":  ["mixtral", "qwen2.5-moe", "qwen3.5", "qwen2.5-coder:14b", "llama3.1"],
    # Vision-language
    # moondream first: reliable on ollama 0.21.x / 8GB; llava's vision runner
    # segfaults on some ollama builds, so it's a lower-priority fallback.
    "VLM":  ["moondream", "qwen2.5-vl", "bakllava", "llava"],
    # Action / tool-calling model — needs solid reasoning, prefer coder/instruct
    "LAM":  ["qwen2.5-coder:14b", "qwen2.5:7b", "llama3.1", "llama3.2"],
}

# Embeddings (MLM/RAG) — Ollama embedding models, else local sentence-transformers
_EMBED_PREFS = ["nomic-embed-text", "mxbai-embed-large", "all-minilm"]

# Tiers that are too weak to comfortably run large (>~9B) models
_HEAVY_MODEL_HINTS = (":14b", ":13b", ":8x7b", ":34b", ":70b", "mixtral", "qwen2.5-coder:14b")


def _ollama_tags(timeout: float = 2.0) -> list[str]:
    """Return installed Ollama model tags, or [] if unreachable."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception as exc:  # noqa: BLE001
        logger.debug("ollama tags unavailable: %s", exc)
        return []


def _ollama_models(timeout: float = 2.0) -> list[dict]:
    """Installed model objects (name + details.quantization_level), or []."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m for m in data.get("models", []) if m.get("name")]
    except Exception as exc:  # noqa: BLE001
        logger.debug("ollama models unavailable: %s", exc)
        return []


def _params_b_from_name(name: str) -> float:
    """Best-effort parameter count (billions) parsed from a model tag, default 7."""
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*b", (name or "").lower())
    return float(m.group(1)) if m else 7.0


# GGUF quant ladder (largest→smallest) — same philosophy as lifecycle_manager.select_quant.
# bytes ≈ params * bpw / 8; pick the largest quant whose weights fit ~75% of VRAM.
_QUANT_TAGS = [("q8_0", 8.5), ("q6_K", 6.6), ("q5_K_M", 5.7),
               ("q4_K_M", 4.8), ("q3_K_M", 3.9), ("q2_K", 3.0)]


def optimal_quant_tag(model_family_or_name: str, tier_or_vram) -> str:
    """Best GGUF quant suffix for a model on this host. Never raises.

    tier_or_vram: a numeric VRAM-GB value, or a tier string (cpu|low|mid|high).
    """
    params_b = _params_b_from_name(model_family_or_name)
    if isinstance(tier_or_vram, (int, float)):
        vram_gb = float(tier_or_vram)
    else:
        vram_gb = {"high": 16.0, "mid": 8.0, "low": 4.0, "cpu": 0.0}.get(str(tier_or_vram), 8.0)
    if vram_gb <= 0:  # CPU host — favour a balanced quant for RAM/speed
        return "q4_K_M"
    budget_mb = vram_gb * 1024 * 0.75
    for name, bpw in _QUANT_TAGS:
        if (params_b * 1e9 * bpw / 8 / 1e6) <= budget_mb:
            return name
    return _QUANT_TAGS[-1][0]


def detect_hardware_tier() -> dict:
    """Return {tier, gpu, vram_gb, ram_gb, cpu_cores}. tier ∈ cpu|low|mid|high."""
    info = {"tier": "cpu", "gpu": None, "vram_gb": 0, "ram_gb": 0, "cpu_cores": os.cpu_count() or 1}
    # RAM
    try:
        import psutil  # type: ignore
        info["ram_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:
        try:
            info["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
        except Exception:
            pass
    # GPU via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4,
            )
            if out.returncode == 0 and out.stdout.strip():
                name, mem = out.stdout.strip().splitlines()[0].split(",")
                info["gpu"] = name.strip()
                info["vram_gb"] = round(float(mem) / 1024, 1)
        except Exception:
            pass
    # Tier
    if info["vram_gb"] >= 16:
        info["tier"] = "high"
    elif info["vram_gb"] >= 8:
        info["tier"] = "mid"
    elif info["vram_gb"] > 0 or info["ram_gb"] >= 32:
        info["tier"] = "low"
    else:
        info["tier"] = "cpu"
    return info


def _match(prefs: list[str], installed: list[str], allow_heavy: bool) -> str | None:
    """First preference whose prefix matches an installed tag (respecting weight limit)."""
    for pref in prefs:
        if not allow_heavy and any(h in pref for h in _HEAVY_MODEL_HINTS):
            continue
        for tag in installed:
            if tag == pref or tag.startswith(pref + ":") or tag.startswith(pref):
                return tag
    return None


def resolve_models() -> dict:
    """Map each architecture to the best runnable model for THIS host.

    Returns: {
      "tier": ..., "hardware": {...},
      "resolved": { "LLM": {model, provider, available, reason}, ... },
      "installed": [tags...]
    }
    """
    hw = detect_hardware_tier()
    installed = _ollama_tags()
    allow_heavy = hw["tier"] in ("mid", "high") or hw["ram_gb"] >= 24
    resolved: dict[str, dict] = {}
    # Real installed quant per tag (best-effort; None if Ollama didn't report it).
    _quant_by_tag = {m.get("name"): (m.get("details") or {}).get("quantization_level")
                     for m in _ollama_models()}

    for arch, prefs in _ARCH_PREFS.items():
        model = _match(prefs, installed, allow_heavy)
        if model is None and not allow_heavy:
            # Heavy filter left nothing — retry allowing heavy as a last resort
            model = _match(prefs, installed, allow_heavy=True)
        active_quant = _quant_by_tag.get(model) if model else None
        resolved[arch] = {
            "model": model,
            "provider": "ollama" if model else None,
            "available": bool(model),
            "active_quant": active_quant,
            "optimal_quant": optimal_quant_tag(model, hw.get("vram_gb", hw["tier"])) if model else None,
            "reason": "installed+tier-fit" if model else "no matching model installed",
        }

    # MLM / RAG embeddings
    embed = _match(_EMBED_PREFS, installed, allow_heavy=True)
    resolved["MLM"] = {
        "model": embed or "sentence-transformers/all-MiniLM-L6-v2",
        "provider": "ollama" if embed else "local",
        "available": True,  # local sentence-transformers fallback always available
        "reason": "ollama-embed" if embed else "local sentence-transformers fallback",
    }

    # LCM (visual generation) + SAM (segmentation): local diffusers / segment-anything.
    # Available when the backing library is importable (weights auto-download on first use).
    import importlib.util as _ilu
    _has = lambda *m: all(_ilu.find_spec(x) is not None for x in m)  # noqa: E731
    if _has("diffusers", "torch"):
        resolved["LCM"] = {
            "model": os.getenv("LCM_MODEL_ID", "SimianLuo/LCM_Dreamshaper_v7"),
            "provider": "diffusers-local", "available": True,
            "reason": "local diffusers (GPU)" if hw.get("gpu") else "local diffusers (CPU — slow)",
        }
    else:
        resolved["LCM"] = {"model": None, "provider": None, "available": False,
                           "reason": "diffusers not installed (pip install diffusers)"}
    if _has("segment_anything", "torch", "cv2"):
        resolved["SAM"] = {
            "model": os.getenv("SAM_MODEL_TYPE", "vit_b"),
            "provider": "segment-anything-local", "available": True,
            "reason": "local segment-anything (weights auto-download)",
        }
    else:
        resolved["SAM"] = {"model": None, "provider": None, "available": False,
                           "reason": "segment-anything not installed (pip install segment-anything)"}

    return {"tier": hw["tier"], "hardware": hw, "installed": installed, "resolved": resolved}


if __name__ == "__main__":
    print(json.dumps(resolve_models(), indent=2))
