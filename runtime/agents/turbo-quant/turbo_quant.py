"""Turbo Quantization — high-efficiency inference optimization layer.

Sits between the AI router and the underlying model backends (Ollama, NVIDIA NIM,
cloud APIs) to maximise throughput and minimise VRAM/CPU cost on mid-tier hardware
such as an RTX 2070 Super (8 GB VRAM) / Ryzen 5 3600 / 16 GB RAM.

Architecture overview
─────────────────────
  ┌─ Turbo Mode ──────────────────────────────────────────────────────────────┐
  │  MONEY  → smallest quantized models, fastest response, lowest cost        │
  │  POWER  → best-quality models, higher latency, full precision where safe  │
  │  AUTO   → dynamically picks based on task complexity & available resources │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Quantization Strategy ───────────────────────────────────────────────────┐
  │  4-bit  (Q4_K_M GGUF) → models ≥ 7 B params, VRAM-constrained tasks     │
  │  8-bit  (Q8_0 GGUF)   → models 1–7 B, quality-sensitive batch tasks      │
  │  FP16   (no quant)    → tiny models < 1 B or CPU-only (dynamic quant)     │
  │  GPTQ / AWQ           → cloud / NIM-hosted models                         │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Model Router ────────────────────────────────────────────────────────────┐
  │  complexity < LOW_THRESHOLD  → lightweight GGUF (Ollama)                  │
  │  complexity < MID_THRESHOLD  → mid-size GGUF (Ollama)                     │
  │  complexity ≥ MID_THRESHOLD  → large model (NVIDIA NIM or cloud)          │
  │  fallback: if quality score below threshold → retry with next-tier model  │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Memory Optimizer ────────────────────────────────────────────────────────┐
  │  • VRAM budget tracking (hard limit: VRAM_BUDGET_GB, default 6.5 GB)      │
  │  • CPU offload suggestion when VRAM headroom is too small                 │
  │  • Lazy-load: only one large model loaded at a time (evict on swap)       │
  │  • Layer-swap hints for AirLLM-style streaming                            │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Inference Acceleration ──────────────────────────────────────────────────┐
  │  • Flash Attention detection & recommendation                             │
  │  • ONNX Runtime path hints                                                │
  │  • Batch-processing adapter (wraps query_ai_batch)                        │
  │  • Token-generation speed target (tokens/sec thresholds per mode)        │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Performance Logger ──────────────────────────────────────────────────────┐
  │  Writes JSONL to ~/.ai-employee/state/turbo_quant.log.jsonl               │
  │  Fields: ts, agent_id, task_category, mode, model, quant, latency_ms,    │
  │           vram_mb, prompt_tokens, response_tokens, quality_score,        │
  │           provider, error                                                 │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Auto-Improvement Loop ───────────────────────────────────────────────────┐
  │  • Analyses recent log entries                                            │
  │  • Calculates per-model efficiency scores                                 │
  │  • Emits config suggestions (no automatic code patching)                  │
  │  • Sandbox-mode dry-run with alternative configs                          │
  └───────────────────────────────────────────────────────────────────────────┘

Environment variables (all optional — sane defaults for RTX 2070 Super)
────────────────────────────────────────────────────────────────────────
  TURBO_MODE               — MONEY | POWER | AUTO  (default: AUTO)
  TURBO_VRAM_BUDGET_GB     — VRAM budget in GB     (default: 6.5)
  TURBO_LOG_MAX_LINES      — max log lines kept     (default: 2000)
  TURBO_LOW_COMPLEXITY     — complexity threshold for lightweight routing
                             (default: 0.3, range 0–1)
  TURBO_MID_COMPLEXITY     — complexity threshold for mid-tier routing
                             (default: 0.65, range 0–1)
  TURBO_QUALITY_THRESHOLD  — min quality score before fallback retry
                             (default: 0.5, range 0–1)
  TURBO_SANDBOX            — 1 = auto-improvement dry-run only (default: 1)

Usage
─────
    import sys, os
    from pathlib import Path
    AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
    sys.path.insert(0, str(AI_HOME / "agents" / "turbo-quant"))
    from turbo_quant import (
        get_mode, set_mode,
        select_model, QuantConfig,
        log_inference, run_auto_improvement,
        memory_status, suggest_acceleration,
    )

    cfg = select_model(agent_id="sales-closer-pro", task="Write a cold email", complexity=0.4)
    print(cfg.model, cfg.quant, cfg.provider)   # e.g. "llama3.2:8b-q4_K_M", "Q4_K_M", "ollama"
"""
from __future__ import annotations

import json
import logging
import math
import os
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
LOG_FILE = STATE_DIR / "turbo_quant.log.jsonl"
SUGGESTIONS_FILE = STATE_DIR / "turbo_quant.suggestions.json"

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("turbo_quant")

# ── Mode constants ─────────────────────────────────────────────────────────────
MODE_MONEY = "MONEY"    # max efficiency — smallest quantized models
MODE_POWER = "POWER"    # max quality  — largest / least-quantized models
MODE_AUTO  = "AUTO"     # dynamic       — picks tier based on task complexity

VALID_MODES = {MODE_MONEY, MODE_POWER, MODE_AUTO}

# ── Quantization levels ────────────────────────────────────────────────────────
QUANT_4BIT  = "Q4_K_M"   # 4-bit GGUF — best size/quality tradeoff ≥7 B
QUANT_5BIT  = "Q5_K_M"   # 5-bit GGUF — good tradeoff, slightly better quality
QUANT_8BIT  = "Q8_0"     # 8-bit GGUF — near-lossless, for smaller models
QUANT_FP16  = "FP16"     # half-precision — tiny models or CPU dynamic quant
QUANT_GPTQ  = "GPTQ"     # GPTQ 4-bit — cloud / NIM-hosted large models
QUANT_AWQ   = "AWQ"      # AWQ 4-bit  — activation-aware, slightly better than GPTQ

# ── Hardware profile (RTX 2070 Super target) ───────────────────────────────────
VRAM_BUDGET_GB: float = float(os.environ.get("TURBO_VRAM_BUDGET_GB", "6.5"))

# Approximate VRAM usage per quantization level (GB per billion parameters)
_VRAM_PER_BPARAM: dict[str, float] = {
    QUANT_4BIT: 0.58,
    QUANT_5BIT: 0.72,
    QUANT_8BIT: 1.10,
    QUANT_FP16: 2.05,
    QUANT_GPTQ: 0.58,
    QUANT_AWQ:  0.55,
}

# ── Complexity thresholds ──────────────────────────────────────────────────────
LOW_COMPLEXITY_THRESHOLD: float = float(os.environ.get("TURBO_LOW_COMPLEXITY", "0.30"))
MID_COMPLEXITY_THRESHOLD: float = float(os.environ.get("TURBO_MID_COMPLEXITY", "0.65"))
QUALITY_THRESHOLD: float = float(os.environ.get("TURBO_QUALITY_THRESHOLD", "0.50"))

# ── Log config ─────────────────────────────────────────────────────────────────
LOG_MAX_LINES: int = int(os.environ.get("TURBO_LOG_MAX_LINES", "2000"))
SANDBOX_MODE: bool = os.environ.get("TURBO_SANDBOX", "1").strip() not in ("0", "false", "no")

# ── Thread safety ──────────────────────────────────────────────────────────────
_mode_lock = threading.Lock()
_log_lock  = threading.Lock()
_loaded_models: dict[str, float] = {}   # model_key → approx VRAM GB consumed
_loaded_lock = threading.Lock()

# ── Active mode (in-process override, overrides env var) ──────────────────────
_active_mode: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class QuantConfig:
    """Describes the chosen model / quantization strategy for a single inference."""
    agent_id:    str = ""
    category:    str = "general"
    mode:        str = MODE_AUTO
    model:       str = ""            # fully-qualified model name (e.g. "llama3.2:8b-q4_K_M")
    base_model:  str = ""            # base model name without quant suffix
    params_b:    float = 0.0         # approximate parameter count in billions
    quant:       str = QUANT_4BIT
    provider:    str = "ollama"      # "ollama" | "nvidia_nim" | "anthropic" | "openai"
    vram_est_gb: float = 0.0         # estimated VRAM consumption
    temperature: float = 0.7
    max_tokens:  int = 1024
    complexity:  float = 0.5
    rationale:   str = ""


@dataclass
class InferenceLog:
    """One recorded inference event."""
    ts:               str   = ""
    agent_id:         str   = ""
    task_category:    str   = "general"
    mode:             str   = MODE_AUTO
    model:            str   = ""
    quant:            str   = ""
    provider:         str   = ""
    latency_ms:       float = 0.0
    vram_mb:          float = 0.0
    prompt_tokens:    int   = 0
    response_tokens:  int   = 0
    quality_score:    float = -1.0   # -1 = not measured
    error:            str   = ""
    complexity:       float = 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Quantization catalogue
# (maps: category → complexity tier → { mode → QuantConfig fields })
# ──────────────────────────────────────────────────────────────────────────────

# Ollama model tags follow the pattern  <base>:<size>-<quant>
# "instruct" variants used where available for chat tasks.
_MODEL_CATALOGUE: dict = {
    # ── lightweight MONEY tier (low complexity) ──────────────────────────────
    "tiny_money": {
        "base_model": "llama3.2",
        "params_b":   3.0,
        "quant":      QUANT_4BIT,
        "model":      "llama3.2:3b-instruct-q4_K_M",
        "provider":   "ollama",
        "temperature": 0.7,
        "max_tokens":  512,
    },
    # ── small MONEY tier (low-mid complexity) ───────────────────────────────
    "small_money": {
        "base_model": "llama3.2",
        "params_b":   8.0,
        "quant":      QUANT_4BIT,
        "model":      "llama3.2:8b-instruct-q4_K_M",
        "provider":   "ollama",
        "temperature": 0.7,
        "max_tokens":  1024,
    },
    # ── mid-size POWER tier (mid complexity) ────────────────────────────────
    "mid_power": {
        "base_model": "llama3.1",
        "params_b":   8.0,
        "quant":      QUANT_8BIT,
        "model":      "llama3.1:8b-instruct-q8_0",
        "provider":   "ollama",
        "temperature": 0.5,
        "max_tokens":  2048,
    },
    # ── large POWER tier (high complexity, NIM) ──────────────────────────────
    "large_power_reasoning": {
        "base_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "params_b":   49.0,
        "quant":      QUANT_GPTQ,
        "model":      "nvidia/llama-3.3-nemotron-super-49b-v1",
        "provider":   "nvidia_nim",
        "temperature": 0.3,
        "max_tokens":  4096,
    },
    # ── large POWER tier (coding, NIM) ──────────────────────────────────────
    "large_power_coding": {
        "base_model": "qwen/qwen2.5-coder-32b-instruct",
        "params_b":   32.0,
        "quant":      QUANT_AWQ,
        "model":      "qwen/qwen2.5-coder-32b-instruct",
        "provider":   "nvidia_nim",
        "temperature": 0.1,
        "max_tokens":  4096,
    },
    # ── cloud fallback (POWER, sales) ────────────────────────────────────────
    "cloud_power_sales": {
        "base_model": "gpt-4o",
        "params_b":   0.0,          # unknown
        "quant":      QUANT_FP16,
        "model":      "gpt-4o",
        "provider":   "openai",
        "temperature": 0.8,
        "max_tokens":  2048,
    },
    # ── cloud fallback (POWER, creative) ─────────────────────────────────────
    "cloud_power_creative": {
        "base_model": "gpt-4o",
        "params_b":   0.0,
        "quant":      QUANT_FP16,
        "model":      "gpt-4o",
        "provider":   "openai",
        "temperature": 0.9,
        "max_tokens":  2048,
    },
    # ── local bulk MONEY tier ─────────────────────────────────────────────────
    "bulk_money": {
        "base_model": "llama3.2",
        "params_b":   3.0,
        "quant":      QUANT_4BIT,
        "model":      "llama3.2:3b-instruct-q4_K_M",
        "provider":   "ollama",
        "temperature": 0.7,
        "max_tokens":  256,
    },
}

# Category → (money_key, mid_key, power_key)
_CATEGORY_TIERS: dict[str, tuple[str, str, str]] = {
    "sales":        ("small_money",   "mid_power",      "cloud_power_sales"),
    "creative":     ("small_money",   "mid_power",      "cloud_power_creative"),
    "analytics":    ("mid_power",     "mid_power",      "large_power_reasoning"),
    "research":     ("mid_power",     "mid_power",      "large_power_reasoning"),
    "reasoning":    ("mid_power",     "large_power_reasoning", "large_power_reasoning"),
    "orchestrator": ("mid_power",     "large_power_reasoning", "large_power_reasoning"),
    "coding":       ("small_money",   "large_power_coding",    "large_power_coding"),
    "bulk":         ("bulk_money",    "bulk_money",     "small_money"),
    "general":      ("tiny_money",    "small_money",    "mid_power"),
}


# ──────────────────────────────────────────────────────────────────────────────
# Mode management
# ──────────────────────────────────────────────────────────────────────────────

def get_mode() -> str:
    """Return the current Turbo Mode (MONEY | POWER | AUTO)."""
    with _mode_lock:
        if _active_mode:
            return _active_mode
    return os.environ.get("TURBO_MODE", MODE_AUTO).upper()


def set_mode(mode: str) -> str:
    """Set the Turbo Mode.  Returns the normalised mode string."""
    global _active_mode
    mode = mode.upper().strip()
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid TURBO_MODE '{mode}'. Valid: {', '.join(sorted(VALID_MODES))}")
    with _mode_lock:
        _active_mode = mode
    logger.info("Turbo mode set to %s", mode)
    return mode


# ──────────────────────────────────────────────────────────────────────────────
# Complexity estimation
# ──────────────────────────────────────────────────────────────────────────────

_COMPLEX_KEYWORDS: frozenset[str] = frozenset({
    "analyse", "analyze", "explain", "compare", "evaluate", "assess",
    "strategy", "strategic", "architecture", "design", "implement",
    "debug", "reason", "infer", "synthesise", "synthesize", "research",
    "deep", "complex", "advanced", "expert", "comprehensive",
})
_SIMPLE_KEYWORDS: frozenset[str] = frozenset({
    "summarise", "summarize", "list", "format", "convert", "translate",
    "rewrite", "classify", "tag", "label", "extract", "simple",
    "quick", "short", "brief", "fast",
})


def estimate_complexity(task: str) -> float:
    """Estimate task complexity on a 0–1 scale from the task description string.

    Returns a float:
      < LOW_COMPLEXITY_THRESHOLD  → lightweight model sufficient
      < MID_COMPLEXITY_THRESHOLD  → mid-tier model
      ≥ MID_COMPLEXITY_THRESHOLD  → large model recommended
    """
    if not task:
        return 0.5
    words = task.lower().split()
    word_set = set(words)

    # Base score: normalised prompt length (longer = more complex, capped at ~200 words)
    length_score = min(len(words) / 200.0, 1.0) * 0.3

    complex_hits = len(word_set & _COMPLEX_KEYWORDS) / max(len(_COMPLEX_KEYWORDS), 1)
    simple_hits  = len(word_set & _SIMPLE_KEYWORDS)  / max(len(_SIMPLE_KEYWORDS),  1)

    keyword_score = complex_hits * 0.6 - simple_hits * 0.3

    return max(0.0, min(1.0, 0.3 + length_score + keyword_score))


# ──────────────────────────────────────────────────────────────────────────────
# VRAM / memory management
# ──────────────────────────────────────────────────────────────────────────────

def vram_estimate_gb(params_b: float, quant: str) -> float:
    """Estimate VRAM consumption for a model given its parameter count and quant level."""
    if params_b <= 0:
        return 0.0
    gb_per_b = _VRAM_PER_BPARAM.get(quant, 1.0)
    return round(params_b * gb_per_b + 0.5, 2)   # +0.5 GB overhead


def memory_status() -> dict:
    """Return a snapshot of tracked VRAM usage across loaded models.

    Note: this tracks *estimated* usage based on what turbo_quant has registered
    via register_loaded_model() / unregister_model().  It does not query the GPU
    directly (no hardware dependency required at import time).
    """
    with _loaded_lock:
        used = sum(_loaded_models.values())
    return {
        "budget_gb":    VRAM_BUDGET_GB,
        "used_est_gb":  round(used, 2),
        "free_est_gb":  round(max(0.0, VRAM_BUDGET_GB - used), 2),
        "loaded_models": dict(_loaded_models),
    }


def register_loaded_model(model_key: str, vram_gb: float) -> None:
    """Notify turbo_quant that a model has been loaded into VRAM."""
    with _loaded_lock:
        _loaded_models[model_key] = vram_gb


def unregister_model(model_key: str) -> None:
    """Notify turbo_quant that a model has been evicted from VRAM."""
    with _loaded_lock:
        _loaded_models.pop(model_key, None)


def _evict_if_needed(needed_gb: float) -> list[str]:
    """Return a list of model keys that should be evicted to fit *needed_gb* into VRAM.

    Does not evict models itself — callers are responsible for actual eviction.
    Returns the keys in LIFO order (most-recently-added first).
    """
    evict: list[str] = []
    with _loaded_lock:
        used = sum(_loaded_models.values())
        if used + needed_gb <= VRAM_BUDGET_GB:
            return evict
        # Evict from the end (LIFO heuristic)
        for key in reversed(list(_loaded_models.keys())):
            evict.append(key)
            used -= _loaded_models[key]
            if used + needed_gb <= VRAM_BUDGET_GB:
                break
    return evict


def should_offload_to_cpu(params_b: float, quant: str) -> bool:
    """Return True when the model would exceed the VRAM budget and CPU offload is recommended."""
    est = vram_estimate_gb(params_b, quant)
    status = memory_status()
    return est > status["free_est_gb"]


# ──────────────────────────────────────────────────────────────────────────────
# Inference acceleration helpers
# ──────────────────────────────────────────────────────────────────────────────

def suggest_acceleration(params_b: float, provider: str, quant: str) -> dict:
    """Return a dict of inference acceleration recommendations.

    This is advisory only — no hardware calls are made.
    """
    tips = []
    use_flash_attn = False
    use_onnx       = False

    if provider == "ollama":
        tips.append("Ollama uses llama.cpp with cuBLAS — GPU layers auto-detected.")
        if params_b >= 7:
            use_flash_attn = True
            tips.append("Enable Flash Attention: set OLLAMA_FLASH_ATTN=1 in .env.")
        if quant in (QUANT_4BIT, QUANT_5BIT):
            tips.append(
                "Q4_K_M / Q5_K_M GGUF recommended for RTX 2070 Super — "
                "matches GPU memory without quality loss."
            )

    elif provider == "nvidia_nim":
        tips.append("NVIDIA NIM uses TensorRT-LLM on server side — no local acceleration needed.")
        use_flash_attn = True  # NIM enables it automatically

    elif provider in ("openai", "anthropic"):
        tips.append("Cloud provider handles acceleration server-side.")

    if params_b > 0 and should_offload_to_cpu(params_b, quant):
        tips.append(
            "Model may exceed VRAM budget. "
            "Consider AirLLM layer-streaming or CPU offload via `--gpu-layers` in Ollama."
        )
        use_onnx = params_b < 4  # ONNX is practical for small CPU models

    if use_onnx:
        tips.append(
            "For CPU inference consider ONNX Runtime with dynamic int8 quantization "
            "(optimum + onnxruntime-gpu)."
        )

    return {
        "flash_attention": use_flash_attn,
        "onnx_recommended": use_onnx,
        "batch_supported": provider == "ollama",
        "tips": tips,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Core model selection
# ──────────────────────────────────────────────────────────────────────────────

def select_model(
    agent_id:   str   = "",
    task:       str   = "",
    category:   str   = "general",
    complexity: Optional[float] = None,
    mode:       Optional[str]   = None,
) -> QuantConfig:
    """Select the optimal model / quantization config for one inference call.

    Args:
        agent_id:   The calling agent's ID (for logging / overrides).
        task:       Free-text description of the task (used to estimate complexity).
        category:   Agent category from ai_router._AGENT_ROUTING.
        complexity: Override 0–1 complexity.  If None, estimated from *task*.
        mode:       Override TURBO_MODE for this call.

    Returns:
        QuantConfig with fully resolved model, quantization level, and provider.
    """
    effective_mode = (mode or get_mode()).upper()
    if effective_mode not in VALID_MODES:
        effective_mode = MODE_AUTO

    if complexity is None:
        complexity = estimate_complexity(task)

    tiers = _CATEGORY_TIERS.get(category, _CATEGORY_TIERS["general"])
    money_key, mid_key, power_key = tiers

    if effective_mode == MODE_MONEY:
        catalogue_key = money_key
    elif effective_mode == MODE_POWER:
        catalogue_key = power_key
    else:
        # AUTO: pick tier by complexity
        if complexity < LOW_COMPLEXITY_THRESHOLD:
            catalogue_key = money_key
        elif complexity < MID_COMPLEXITY_THRESHOLD:
            catalogue_key = mid_key
        else:
            catalogue_key = power_key

    spec = _MODEL_CATALOGUE[catalogue_key]
    params_b  = spec["params_b"]
    quant     = spec["quant"]
    vram_est  = vram_estimate_gb(params_b, quant)

    # If estimated VRAM exceeds budget and the provider is local, downgrade to money tier
    if vram_est > VRAM_BUDGET_GB and spec["provider"] == "ollama" and catalogue_key != money_key:
        logger.warning(
            "VRAM budget exceeded (%.1f GB > %.1f GB) — downgrading to MONEY tier.",
            vram_est,
            VRAM_BUDGET_GB,
        )
        spec     = _MODEL_CATALOGUE[money_key]
        params_b = spec["params_b"]
        quant    = spec["quant"]
        vram_est = vram_estimate_gb(params_b, quant)

    rationale = (
        f"mode={effective_mode}, complexity={complexity:.2f}, "
        f"category={category}, catalogue={catalogue_key}"
    )

    return QuantConfig(
        agent_id    = agent_id,
        category    = category,
        mode        = effective_mode,
        model       = spec["model"],
        base_model  = spec["base_model"],
        params_b    = params_b,
        quant       = quant,
        provider    = spec["provider"],
        vram_est_gb = vram_est,
        temperature = spec["temperature"],
        max_tokens  = spec["max_tokens"],
        complexity  = complexity,
        rationale   = rationale,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Performance logger
# ──────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_inference(
    agent_id:        str   = "",
    task_category:   str   = "general",
    mode:            str   = "",
    model:           str   = "",
    quant:           str   = "",
    provider:        str   = "",
    latency_ms:      float = 0.0,
    vram_mb:         float = 0.0,
    prompt_tokens:   int   = 0,
    response_tokens: int   = 0,
    quality_score:   float = -1.0,
    error:           str   = "",
    complexity:      float = 0.5,
) -> None:
    """Append one inference record to the JSONL performance log.

    All arguments are keyword-only.  Unknown / zero fields are stored as-is.
    """
    entry = InferenceLog(
        ts              = _now_iso(),
        agent_id        = agent_id,
        task_category   = task_category,
        mode            = mode or get_mode(),
        model           = model,
        quant           = quant,
        provider        = provider,
        latency_ms      = latency_ms,
        vram_mb         = vram_mb,
        prompt_tokens   = prompt_tokens,
        response_tokens = response_tokens,
        quality_score   = quality_score,
        error           = error,
        complexity      = complexity,
    )
    _write_log(entry)


def _write_log(entry: InferenceLog) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
    with _log_lock:
        # Append
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line)
        # Trim if over limit
        _trim_log()


def _trim_log() -> None:
    """Keep only the last LOG_MAX_LINES lines in the log file."""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(lines) > LOG_MAX_LINES:
            LOG_FILE.write_text(
                "".join(lines[-LOG_MAX_LINES:]), encoding="utf-8"
            )
    except OSError:
        pass


def read_recent_logs(n: int = 200) -> list[dict]:
    """Return the *n* most recent inference log entries as dicts."""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= n:
            break
    return list(reversed(out))


# ──────────────────────────────────────────────────────────────────────────────
# Context-manager helper for timing + auto-logging
# ──────────────────────────────────────────────────────────────────────────────

class InferenceTimer:
    """Context manager that automatically logs timing on exit.

    Usage::

        with InferenceTimer(agent_id="sales-closer-pro", cfg=cfg) as timer:
            result = query_ai(prompt)
            timer.response_tokens = len(result["answer"].split())
            timer.quality_score = 0.8
    """

    def __init__(self, agent_id: str = "", cfg: Optional[QuantConfig] = None) -> None:
        self.agent_id       = agent_id
        self.cfg            = cfg or QuantConfig()
        self.response_tokens: int   = 0
        self.prompt_tokens:   int   = 0
        self.quality_score:   float = -1.0
        self.error:           str   = ""
        self._start: float = 0.0

    def __enter__(self) -> "InferenceTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000.0
        if exc_val:
            self.error = str(exc_val)
        log_inference(
            agent_id        = self.agent_id or self.cfg.agent_id,
            task_category   = self.cfg.category,
            mode            = self.cfg.mode,
            model           = self.cfg.model,
            quant           = self.cfg.quant,
            provider        = self.cfg.provider,
            latency_ms      = round(elapsed_ms, 1),
            prompt_tokens   = self.prompt_tokens,
            response_tokens = self.response_tokens,
            quality_score   = self.quality_score,
            error           = self.error,
            complexity      = self.cfg.complexity,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Quantization recommendation helpers (for documentation / UI)
# ──────────────────────────────────────────────────────────────────────────────

def recommend_quant_format(params_b: float, task_type: str = "general") -> dict:
    """Return a recommendation dict for the best quantization format.

    This is advisory — helps operators choose models in Ollama or for download.

    Args:
        params_b:  Model parameter count in billions.
        task_type: One of general | coding | reasoning | bulk.

    Returns a dict with ``format``, ``gguf_tag``, ``rationale``, and
    ``ollama_pull_cmd``.
    """
    if params_b <= 0:
        return {"format": QUANT_FP16, "gguf_tag": "", "rationale": "Unknown model size — defaulting to FP16.", "ollama_pull_cmd": ""}

    vram_4bit = vram_estimate_gb(params_b, QUANT_4BIT)
    vram_8bit = vram_estimate_gb(params_b, QUANT_8BIT)

    if params_b >= 30:
        fmt   = QUANT_GPTQ
        tag   = ""
        rationale = (
            f"{params_b:.0f}B parameter model exceeds local VRAM budget — "
            "recommend GPTQ/AWQ via NVIDIA NIM or cloud endpoint."
        )
        pull_cmd = f"# Model too large for local 8 GB VRAM — use NVIDIA NIM or cloud API"
    elif vram_4bit <= VRAM_BUDGET_GB * 0.85:
        fmt   = QUANT_4BIT
        tag   = "q4_K_M"
        rationale = (
            f"Q4_K_M uses ~{vram_4bit:.1f} GB VRAM — fits comfortably on RTX 2070 Super. "
            "Best size/quality tradeoff for mid-size models."
        )
        base_name = "llama3.2" if params_b <= 4 else "llama3.1"
        size_tag  = f"{int(params_b)}b"
        pull_cmd  = f"ollama pull {base_name}:{size_tag}-instruct-q4_K_M"
    elif vram_8bit <= VRAM_BUDGET_GB * 0.85:
        fmt   = QUANT_8BIT
        tag   = "q8_0"
        rationale = (
            f"Q8_0 uses ~{vram_8bit:.1f} GB VRAM — near-lossless quality. "
            "Recommended for quality-sensitive tasks on smaller models."
        )
        base_name = "llama3.2"
        size_tag  = f"{int(params_b)}b"
        pull_cmd  = f"ollama pull {base_name}:{size_tag}-instruct-q8_0"
    else:
        fmt   = QUANT_FP16
        tag   = "fp16"
        rationale = (
            f"Even Q8_0 ({vram_8bit:.1f} GB) exceeds VRAM budget. "
            "Use CPU offload or AirLLM layer streaming."
        )
        pull_cmd = f"# Enable CPU offload: OLLAMA_GPU_LAYERS=<N> in .env"

    return {
        "format":         fmt,
        "gguf_tag":       tag,
        "rationale":      rationale,
        "ollama_pull_cmd": pull_cmd,
        "vram_est_gb":    round(vram_4bit if fmt == QUANT_4BIT else vram_8bit, 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# AirLLM integration hints
# ──────────────────────────────────────────────────────────────────────────────

def airllm_config(params_b: float, quant: str = QUANT_4BIT) -> dict:
    """Return recommended AirLLM configuration for a given model size.

    AirLLM streams model layers from disk to GPU one at a time, enabling
    inference on large models with limited VRAM.
    """
    compression = "4bit" if quant in (QUANT_4BIT, QUANT_GPTQ, QUANT_AWQ) else "8bit"
    return {
        "library":           "airllm",
        "compression":       compression,
        "prefetch_layers":   2,
        "max_gpu_layers":    int(VRAM_BUDGET_GB / 0.5),   # rough heuristic
        "recommended":       params_b > VRAM_BUDGET_GB / _VRAM_PER_BPARAM.get(quant, 1.0),
        "install_cmd":       "pip install airllm",
        "example": (
            f"from airllm import AutoModel\n"
            f"model = AutoModel.from_pretrained('<hf-model-id>', compression='{compression}')\n"
            f"output = model.generate(inputs, max_length=200)"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Auto-improvement loop
# ──────────────────────────────────────────────────────────────────────────────

def _analyse_logs(entries: list[dict]) -> dict:
    """Analyse inference log entries and return efficiency statistics per model."""
    stats: dict[str, dict] = {}
    for e in entries:
        key = e.get("model", "unknown")
        if key not in stats:
            stats[key] = {
                "model":    key,
                "quant":    e.get("quant", ""),
                "provider": e.get("provider", ""),
                "count":    0,
                "latencies": [],
                "quality_scores": [],
                "errors":   0,
            }
        s = stats[key]
        s["count"] += 1
        lat = e.get("latency_ms", 0.0)
        if lat > 0:
            s["latencies"].append(lat)
        qs = e.get("quality_score", -1.0)
        if qs >= 0:
            s["quality_scores"].append(qs)
        if e.get("error"):
            s["errors"] += 1

    summary = {}
    for key, s in stats.items():
        lats = s["latencies"]
        qss  = s["quality_scores"]
        summary[key] = {
            "model":           s["model"],
            "quant":           s["quant"],
            "provider":        s["provider"],
            "count":           s["count"],
            "avg_latency_ms":  round(statistics.mean(lats), 1)  if lats else 0.0,
            "p95_latency_ms":  round(sorted(lats)[int(len(lats) * 0.95)], 1) if lats else 0.0,
            "avg_quality":     round(statistics.mean(qss), 3)   if qss  else -1.0,
            "error_rate":      round(s["errors"] / s["count"], 3),
        }
    return summary


def _build_suggestions(stats: dict) -> list[dict]:
    """Turn efficiency stats into human-readable config suggestions."""
    suggestions = []
    for key, s in stats.items():
        issues = []

        if s["avg_latency_ms"] > 5000 and s["provider"] == "ollama":
            issues.append(
                f"High avg latency ({s['avg_latency_ms']:.0f} ms). "
                "Try downgrading to Q4_K_M or reducing max_tokens."
            )

        if 0 <= s["avg_quality"] < QUALITY_THRESHOLD:
            issues.append(
                f"Low quality score ({s['avg_quality']:.2f} < {QUALITY_THRESHOLD}). "
                "Consider upgrading to a larger model or switching to Q8_0."
            )

        if s["error_rate"] > 0.1:
            issues.append(
                f"High error rate ({s['error_rate']:.1%}). "
                "Check VRAM headroom and model availability in Ollama."
            )

        if issues:
            suggestions.append({
                "model":   key,
                "issues":  issues,
                "sandbox": SANDBOX_MODE,
            })
    return suggestions


def run_auto_improvement(recent_n: int = 500) -> dict:
    """Analyse recent inference logs and generate config improvement suggestions.

    In SANDBOX_MODE (default: True) no changes are applied — suggestions are
    written to ~/.ai-employee/state/turbo_quant.suggestions.json only.

    Returns a dict with ``stats`` and ``suggestions``.
    """
    entries = read_recent_logs(recent_n)
    if not entries:
        return {"stats": {}, "suggestions": [], "message": "No log entries yet."}

    stats       = _analyse_logs(entries)
    suggestions = _build_suggestions(stats)

    result = {
        "analysed":    len(entries),
        "models_seen": len(stats),
        "stats":       stats,
        "suggestions": suggestions,
        "sandbox":     SANDBOX_MODE,
        "ts":          _now_iso(),
    }

    # Persist suggestions
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        SUGGESTIONS_FILE.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not write suggestions file: %s", exc)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Convenience: mode-aware query wrapper
# ──────────────────────────────────────────────────────────────────────────────

def turbo_query(
    prompt:     str,
    agent_id:   str   = "",
    category:   str   = "general",
    complexity: Optional[float] = None,
    mode:       Optional[str]   = None,
    query_fn=None,
) -> dict:
    """Select the best model for *prompt* and call *query_fn* with it.

    *query_fn* should accept ``(prompt, model, provider, temperature, max_tokens)``
    keyword arguments and return a dict with at least ``{"answer": str, "provider": str}``.
    If *query_fn* is None a stub response is returned (useful for testing).

    Returns the raw result from *query_fn* augmented with ``turbo_config`` and
    ``latency_ms`` keys.
    """
    cfg = select_model(
        agent_id   = agent_id,
        task       = prompt,
        category   = category,
        complexity = complexity,
        mode       = mode,
    )

    if query_fn is None:
        return {
            "answer":       "(turbo_query stub — no query_fn provided)",
            "provider":     cfg.provider,
            "turbo_config": asdict(cfg),
            "latency_ms":   0.0,
        }

    with InferenceTimer(agent_id=agent_id, cfg=cfg) as timer:
        result = query_fn(
            prompt,
            model       = cfg.model,
            provider    = cfg.provider,
            temperature = cfg.temperature,
            max_tokens  = cfg.max_tokens,
        )
        timer.response_tokens = len(result.get("answer", "").split())

    result["turbo_config"] = asdict(cfg)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Module self-test (python3 turbo_quant.py)
# ──────────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    print("── Turbo Quant self-test ──────────────────────────────")

    # Mode management
    set_mode(MODE_MONEY)
    assert get_mode() == MODE_MONEY, "set_mode failed"
    set_mode(MODE_AUTO)

    # Complexity estimation
    c_simple  = estimate_complexity("summarize this")
    c_complex = estimate_complexity(
        "Analyse and synthesize the strategic architecture of a deep reasoning system "
        "to evaluate multi-agent orchestration design for complex business scenarios"
    )
    assert c_simple < c_complex, f"complexity ordering failed: {c_simple} >= {c_complex}"
    print(f"  complexity simple={c_simple:.2f}  complex={c_complex:.2f}  ✓")

    # Model selection
    cfg_money = select_model(category="general", mode=MODE_MONEY)
    cfg_power = select_model(category="reasoning", mode=MODE_POWER)
    assert cfg_money.provider == "ollama",       f"money tier should be ollama, got {cfg_money.provider}"
    assert cfg_power.provider == "nvidia_nim",   f"power tier reasoning should be nvidia_nim, got {cfg_power.provider}"
    assert cfg_money.params_b <= cfg_power.params_b or cfg_power.params_b == 0, "power should be larger"
    print(f"  money  model={cfg_money.model}  quant={cfg_money.quant}  ✓")
    print(f"  power  model={cfg_power.model}  quant={cfg_power.quant}  ✓")

    # VRAM estimate
    est = vram_estimate_gb(7.0, QUANT_4BIT)
    assert 0 < est < 10, f"VRAM estimate out of range: {est}"
    print(f"  VRAM estimate 7B Q4_K_M = {est:.2f} GB  ✓")

    # Memory status
    register_loaded_model("test-model", 3.0)
    status = memory_status()
    assert status["used_est_gb"] == 3.0, f"memory tracking failed: {status}"
    unregister_model("test-model")
    assert memory_status()["used_est_gb"] == 0.0, "unregister failed"
    print("  memory tracking  ✓")

    # Suggest acceleration
    accel = suggest_acceleration(7.0, "ollama", QUANT_4BIT)
    assert accel["flash_attention"] is True
    assert accel["batch_supported"] is True
    print("  acceleration hints  ✓")

    # Quantization recommendation
    rec = recommend_quant_format(7.0)
    assert rec["format"] in (QUANT_4BIT, QUANT_5BIT, QUANT_8BIT)
    print(f"  recommend_quant 7B = {rec['format']} ({rec['ollama_pull_cmd']})  ✓")

    # AirLLM config
    air = airllm_config(70.0, QUANT_4BIT)
    assert air["recommended"] is True
    print(f"  airllm_config 70B recommended={air['recommended']}  ✓")

    # Logging (writes to /tmp to avoid polluting production state)
    import tempfile
    global LOG_FILE, STATE_DIR
    orig_log  = LOG_FILE
    orig_dir  = STATE_DIR
    with tempfile.TemporaryDirectory() as td:
        STATE_DIR = Path(td)
        LOG_FILE  = Path(td) / "test.log.jsonl"
        log_inference(agent_id="test", model="test-model", quant=QUANT_4BIT, provider="ollama", latency_ms=123.4)
        entries = read_recent_logs(10)
        assert len(entries) == 1
        assert entries[0]["latency_ms"] == 123.4
        print("  logging  ✓")

        result = run_auto_improvement(recent_n=10)
        assert "stats" in result
        print("  auto-improvement  ✓")
    LOG_FILE  = orig_log
    STATE_DIR = orig_dir

    print("── All turbo_quant self-tests passed ✓ ──────────────")


if __name__ == "__main__":
    _selftest()
