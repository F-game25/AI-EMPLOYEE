"""Turbo Quantization — high-efficiency inference optimization layer.

Sits between the AI router and the underlying model backends (Ollama, NVIDIA NIM,
cloud APIs) to maximise throughput and minimise VRAM/CPU cost.  Hardware specs are
auto-detected at startup so the module works on any machine — from a low-end laptop
with no GPU to a high-end workstation with a 24 GB card.

Hardware Detection
──────────────────
  detect_hardware() runs once at import time and returns a HardwareProfile:
    • GPU VRAM  — tries nvidia-smi (NVIDIA), rocm-smi (AMD), system_profiler (macOS),
                  /proc/driver/nvidia (Linux), wmic (Windows). Falls back to 0 (CPU only).
    • RAM       — reads /proc/meminfo (Linux/macOS) or wmic (Windows).
    • CPU cores — os.cpu_count().
    • Platform  — platform.system() + platform.machine().

  The detected VRAM is used automatically as VRAM_BUDGET_GB unless
  TURBO_VRAM_BUDGET_GB is set explicitly in the environment / .env.

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
  │  • VRAM budget auto-detected from hardware (override: TURBO_VRAM_BUDGET_GB)│
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

  ┌─ Offline Mode ────────────────────────────────────────────────────────────┐
  │  Activated via set_offline_mode(True) or TURBO_OFFLINE=1 env var.        │
  │  • Forces full quantization (Q4_K_M minimum)                             │
  │  • Reduces context window to conserve RAM                                │
  │  • Disables all cloud provider paths                                     │
  │  • Enables disk offload hints for very large models                      │
  └───────────────────────────────────────────────────────────────────────────┘

  ┌─ Quant Config JSON ───────────────────────────────────────────────────────┐
  │  Persisted at ~/.ai-employee/config/turbo_quant_config.json              │
  │  Load: load_quant_config() / Save: save_quant_config()                   │
  │  Keys: mode, cpu_ram, gpu_vram, target, offline, context_limit           │
  └───────────────────────────────────────────────────────────────────────────┘

Environment variables (all optional — auto-detected from hardware by default)
──────────────────────────────────────────────────────────────────────────────
  TURBO_MODE               — MONEY | POWER | AUTO  (default: AUTO)
  TURBO_OFFLINE            — 1 = offline mode (no cloud providers, max quant)
  TURBO_VRAM_BUDGET_GB     — override detected VRAM budget in GB
                             (default: auto-detected, or 0.0 for CPU-only)
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
        detect_hardware, hardware_profile,
        select_model, QuantConfig,
        log_inference, run_auto_improvement,
        memory_status, suggest_acceleration,
        set_offline_mode, is_offline_mode,
        load_quant_config, save_quant_config,
        select_quant, disk_offload_config,
    )

    hw = hardware_profile()
    print(hw.gpu_name, hw.vram_gb, hw.ram_gb, hw.cpu_cores)

    cfg = select_model(agent_id="sales-closer-pro", task="Write a cold email", complexity=0.4)
    print(cfg.model, cfg.quant, cfg.provider)   # auto-tuned for your GPU

    # Offline mode (no internet / cloud providers)
    set_offline_mode(True)
    cfg = select_model(agent_id="sales-closer-pro", task="Write a cold email")
    # provider will always be "ollama"; quant forced to Q4_K_M or smaller
"""
from __future__ import annotations

import json
import logging
import math
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR  = AI_HOME / "state"
CONFIG_DIR = AI_HOME / "config"
LOG_FILE = STATE_DIR / "turbo_quant.log.jsonl"
SUGGESTIONS_FILE = STATE_DIR / "turbo_quant.suggestions.json"
QUANT_CONFIG_FILE = CONFIG_DIR / "turbo_quant_config.json"

# ── Default quantization config (saved / loaded as JSON) ──────────────────────
_DEFAULT_QUANT_CONFIG: dict = {
    "mode":          "auto",    # "auto" | "money" | "power"
    "cpu_ram":       "auto",    # "auto" or e.g. "16GB"
    "gpu_vram":      "auto",    # "auto" or e.g. "6GB"
    "target":        "max_performance",  # "max_performance" | "max_quality" | "balanced"
    "offline":       False,     # force offline mode
    "context_limit": 0,         # 0 = no limit; positive int = max context tokens
}

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

# Approximate VRAM usage per quantization level (GB per billion parameters)
_VRAM_PER_BPARAM: dict[str, float] = {
    QUANT_4BIT: 0.58,
    QUANT_5BIT: 0.72,
    QUANT_8BIT: 1.10,
    QUANT_FP16: 2.05,
    QUANT_GPTQ: 0.58,
    QUANT_AWQ:  0.55,
}


# ──────────────────────────────────────────────────────────────────────────────
# Hardware detection — universal, zero external dependencies
# ──────────────────────────────────────────────────────────────────────────────

# Conservative VRAM budget estimates used when a GPU is detected via lspci but
# memory size cannot be queried precisely (no rocm-smi / nvidia-smi available).
_DEFAULT_INTEL_VRAM_GB:    float = 2.0    # Intel integrated GPU (shares system RAM)
_DEFAULT_DISCRETE_GPU_VRAM_GB: float = 4.0  # NVIDIA / AMD discrete GPU without driver tools

# Apple Silicon unified memory fraction used as effective GPU budget.
_APPLE_SILICON_UNIFIED_MEMORY_FRACTION: float = 0.7

# PCI BAR size thresholds — BARs outside this range are not VRAM.
_MIN_VRAM_BAR_GB: float = 0.5    # skip BARs smaller than 512 MB
_MAX_VRAM_BAR_GB: float = 80.0   # skip BARs larger than 80 GB (implausible for consumer GPU)

# CPU inference budget fractions (used when no GPU is detected).
_CPU_INFERENCE_RAM_FRACTION: float = 0.5   # use 50% of RAM as effective Ollama CPU budget
_CPU_INFERENCE_MAX_GB:       float = 16.0  # cap at 16 GB regardless of RAM size

# Common paths where nvidia-smi may live across Linux distros, WSL, and Windows.
_NVIDIA_SMI_CANDIDATES: list[str] = [
    "nvidia-smi",
    "/usr/bin/nvidia-smi",
    "/usr/local/bin/nvidia-smi",
    "/usr/lib/nvidia/nvidia-smi",
    "/opt/cuda/bin/nvidia-smi",
    "/usr/lib/wsl/lib/nvidia-smi",            # WSL2
    r"C:\Windows\System32\nvidia-smi.exe",    # Windows
    r"C:\Windows\SysWOW64\nvidia-smi.exe",
]

# NVIDIA PCI vendor ID (hex)
_NVIDIA_VENDOR_ID: str = "0x10de"

@dataclass
class HardwareProfile:
    """Detected hardware specifications for this machine."""
    gpu_name:    str   = "unknown"   # GPU model name (or "CPU only")
    gpu_vendor:  str   = "unknown"   # "nvidia" | "amd" | "apple" | "intel" | "none"
    vram_gb:     float = 0.0         # detected VRAM in GB (0 = no dedicated GPU)
    ram_gb:      float = 0.0         # total system RAM in GB
    cpu_cores:   int   = 1           # logical CPU core count
    cpu_name:    str   = "unknown"   # CPU model string
    os_name:     str   = "unknown"   # OS name + version
    detection:   str   = "auto"      # "auto" | "env_override" | "fallback"


def _run(cmd: list[str], timeout: int = 5) -> str:
    """Run *cmd* and return stdout, empty string on any failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _detect_vram_nvidia() -> tuple[float, str]:
    """Return (vram_gb, gpu_name) for NVIDIA GPUs.

    Tries (in order):
      1. pynvml Python library (most reliable, works in containers)
      2. nvidia-smi at several common filesystem paths
      3. /proc/driver/nvidia/gpus/*/information (loaded-driver read)
      4. PCI sysfs resource files for NVIDIA vendor (0x10de)
      5. lspci -v — parses BAR size from PCI device description
    """
    # ── 1. pynvml (optional) ───────────────────────────────────────────────────
    try:
        import pynvml  # type: ignore[import]
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count > 0:
            best_mem  = 0
            best_name = ""
            for i in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode()
                if info.total > best_mem:
                    best_mem  = info.total
                    best_name = name
            pynvml.nvmlShutdown()
            if best_mem > 0:
                return round(best_mem / (1024 ** 3), 2), best_name
    except Exception:
        pass

    # ── 2. nvidia-smi at multiple paths ───────────────────────────────────────
    for smi in _NVIDIA_SMI_CANDIDATES:
        mem  = _run([smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
        name = _run([smi, "--query-gpu=name",         "--format=csv,noheader"])
        if mem:
            try:
                vals = [float(v.strip()) for v in mem.splitlines() if v.strip()]
                if vals:
                    gpu_name = name.splitlines()[0].strip() if name else "NVIDIA GPU"
                    return round(max(vals) / 1024, 2), gpu_name
            except ValueError:
                pass

    # ── 3. /proc/driver/nvidia/gpus/*/information ─────────────────────────────
    v, n = _detect_vram_nvidia_proc()
    if v > 0:
        return v, n

    # ── 4. PCI sysfs resource file (NVIDIA vendor 0x10de) ─────────────────────
    v, n = _detect_vram_nvidia_pci_sysfs()
    if v > 0:
        return v, n

    # ── 5. lspci -v BAR parsing ────────────────────────────────────────────────
    v, n = _detect_vram_lspci_bar("nvidia", "NVIDIA GPU")
    if v > 0:
        return v, n

    return 0.0, ""


def _detect_vram_nvidia_proc() -> tuple[float, str]:
    """Read VRAM from /proc/driver/nvidia/gpus/*/information (Linux NVIDIA driver)."""
    gpu_path = Path("/proc/driver/nvidia/gpus")
    if not gpu_path.exists():
        return 0.0, ""
    try:
        best_mb   = 0.0
        best_name = ""
        for info_file in gpu_path.glob("*/information"):
            text = info_file.read_text()
            for line in text.splitlines():
                low = line.lower()
                if low.startswith("model:"):
                    best_name = line.split(":", 1)[-1].strip()
                if "video memory" in low:
                    # "Video Memory: 8192 MB"
                    digits = "".join(c for c in line if c.isdigit())
                    if digits:
                        mb = float(digits)
                        if mb > best_mb:
                            best_mb = mb
        if best_mb > 0:
            return round(best_mb / 1024, 2), best_name or "NVIDIA GPU"
    except Exception:
        pass
    return 0.0, ""


def _detect_vram_nvidia_pci_sysfs() -> tuple[float, str]:
    """Read NVIDIA VRAM from PCI sysfs resource file (Linux, no driver tools needed).

    The NVIDIA GPU exposes its VRAM as BAR1 (256-MB-aligned) or BAR6 in the
    /sys/bus/pci/devices/<id>/resource file.  We read the largest BAR for any
    device with NVIDIA vendor ID (0x10de).
    """
    if platform.system() != "Linux":
        return 0.0, ""
    try:
        pci_root = Path("/sys/bus/pci/devices")
        if not pci_root.exists():
            return 0.0, ""
        best_gb   = 0.0
        best_name = ""
        for dev in pci_root.iterdir():
            vendor_file = dev / "vendor"
            if not vendor_file.exists():
                continue
            if vendor_file.read_text().strip().lower() != _NVIDIA_VENDOR_ID:
                continue
            # Check device class — 0x03xx is display
            class_file = dev / "class"
            if class_file.exists():
                cls = class_file.read_text().strip()
                if not cls.startswith("0x03"):   # 0x0300 VGA, 0x0302 3D, 0x0380 other display
                    continue
            resource_file = dev / "resource"
            if not resource_file.exists():
                continue
            lines = resource_file.read_text().splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 3:
                    continue
                try:
                    start = int(parts[0], 16)
                    end   = int(parts[1], 16)
                    if start == 0 or end == 0:
                        continue
                    size_gb = (end - start + 1) / (1024 ** 3)
                    # Skip implausible BAR sizes (not VRAM)
                    if _MIN_VRAM_BAR_GB <= size_gb <= _MAX_VRAM_BAR_GB and size_gb > best_gb:
                        best_gb = size_gb
                except ValueError:
                    continue
        if best_gb > 0:
            return round(best_gb, 2), "NVIDIA GPU"
    except Exception:
        pass
    return 0.0, ""


def _detect_vram_lspci_bar(vendor_keyword: str, default_name: str) -> tuple[float, str]:
    """Parse `lspci -v` output to find the largest memory BAR for a vendor."""
    if platform.system() != "Linux":
        return 0.0, ""
    out = _run(["lspci", "-v"])
    if not out:
        return 0.0, ""
    best_gb   = 0.0
    best_name = default_name
    in_device = False
    for line in out.splitlines():
        low = line.lower()
        if not line.startswith("\t") and not line.startswith(" "):
            # New device line
            in_device = vendor_keyword.lower() in low
            if in_device:
                # Extract name after last ':'
                parts = line.split(":")
                if len(parts) >= 3:
                    best_name = ":".join(parts[2:]).strip()
        elif in_device and ("memory at" in low or "prefetchable" in low):
            # "Memory at ... [size=8G]"
            import re
            m = re.search(r"\[size=(\d+)([KMGT])\]", line, re.IGNORECASE)
            if m:
                num  = float(m.group(1))
                unit = m.group(2).upper()
                mult = {"K": 1/1024**2, "M": 1/1024, "G": 1.0, "T": 1024.0}.get(unit, 0)
                size_gb = num * mult
                if _MIN_VRAM_BAR_GB <= size_gb <= _MAX_VRAM_BAR_GB and size_gb > best_gb:
                    best_gb = size_gb
    return (round(best_gb, 2), best_name) if best_gb > 0 else (0.0, "")


def _detect_vram_amd() -> tuple[float, str]:
    """Return (vram_gb, gpu_name) for AMD GPUs.

    Tries (in order):
      1. /sys/class/drm/card*/device/mem_info_vram_total (most reliable, no tools needed)
      2. rocm-smi
      3. lspci -v BAR parsing
    """
    # ── 1. DRM sysfs (works without ROCm drivers) ─────────────────────────────
    try:
        import glob as _glob
        best_bytes = 0
        best_name  = ""
        for vram_file in _glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
            try:
                val = int(Path(vram_file).read_text().strip())
                if val > best_bytes:
                    best_bytes = val
                    # Try to read GPU name from same device dir
                    vendor_file = Path(vram_file).parent / "mem_info_vram_vendor"
                    if vendor_file.exists():
                        best_name = vendor_file.read_text().strip()
            except (ValueError, OSError):
                continue
        if best_bytes > 0:
            return round(best_bytes / (1024 ** 3), 2), best_name or "AMD GPU"
    except Exception:
        pass

    # ── 2. rocm-smi ────────────────────────────────────────────────────────────
    out = _run(["rocm-smi", "--showmeminfo", "vram", "--csv"])
    if out:
        try:
            for line in out.splitlines():
                parts = line.split(",")
                if len(parts) >= 2 and parts[-1].strip().isdigit():
                    return round(int(parts[-1].strip()) / (1024 ** 3), 2), "AMD GPU"
        except Exception:
            pass

    # ── 3. lspci BAR ──────────────────────────────────────────────────────────
    v, n = _detect_vram_lspci_bar("amd", "AMD GPU")
    if v > 0:
        return v, n

    return 0.0, ""


def _detect_vram_apple() -> tuple[float, str]:
    """Return (vram_gb, gpu_name) on macOS using system_profiler."""
    if platform.system() != "Darwin":
        return 0.0, ""
    out = _run(["system_profiler", "SPDisplaysDataType"])
    if out:
        gpu_name = "Apple GPU"
        for line in out.splitlines():
            low = line.lower()
            if "chipset model" in low or "gpu" in low:
                gpu_name = line.split(":")[-1].strip()
            if "vram" in low and "mb" in low:
                try:
                    mb = float("".join(c for c in line if c.isdigit() or c == "."))
                    return round(mb / 1024, 2), gpu_name
                except ValueError:
                    pass
            if "total number of cores" in low:
                # Apple Silicon — estimate ~70% of RAM as unified GPU memory
                pass
    # Apple Silicon unified memory: treat available system RAM × fraction as VRAM
    ram = _detect_ram_gb()
    if ram > 0 and (platform.machine() == "arm64" or "Apple" in (platform.processor() or "")):
        return round(ram * _APPLE_SILICON_UNIFIED_MEMORY_FRACTION, 2), "Apple Silicon"
    return 0.0, ""


def _detect_vram_windows_wmic() -> tuple[float, str]:
    """Return (vram_gb, gpu_name) on Windows via wmic."""
    if platform.system() != "Windows":
        return 0.0, ""
    out = _run(["wmic", "path", "win32_VideoController", "get", "AdapterRAM,Name", "/format:csv"])
    if out:
        for line in out.splitlines():
            parts = line.split(",")
            if len(parts) >= 3:
                try:
                    ram_bytes = int(parts[1].strip())
                    name = parts[2].strip()
                    if ram_bytes > 0:
                        return round(ram_bytes / (1024 ** 3), 2), name
                except (ValueError, IndexError):
                    pass
    return 0.0, ""


def _detect_ram_gb() -> float:
    """Return total system RAM in GB across Linux, macOS, and Windows."""
    sys_name = platform.system()

    if sys_name in ("Linux", "Darwin"):
        # /proc/meminfo (Linux)
        try:
            with open("/proc/meminfo", "r") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 2)
        except OSError:
            pass
        # sysctl (macOS)
        out = _run(["sysctl", "-n", "hw.memsize"])
        if out:
            try:
                return round(int(out) / (1024 ** 3), 2)
            except ValueError:
                pass

    elif sys_name == "Windows":
        out = _run(["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"])
        for line in out.splitlines():
            if "TotalPhysicalMemory=" in line:
                try:
                    return round(int(line.split("=")[1]) / (1024 ** 3), 2)
                except (ValueError, IndexError):
                    pass

    return 0.0


def _detect_cpu_name() -> str:
    """Return CPU model string."""
    sys_name = platform.system()

    if sys_name == "Linux":
        try:
            with open("/proc/cpuinfo", "r") as fh:
                for line in fh:
                    if "model name" in line.lower():
                        return line.split(":", 1)[-1].strip()
        except OSError:
            pass

    elif sys_name == "Darwin":
        out = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if out:
            return out

    elif sys_name == "Windows":
        out = _run(["wmic", "cpu", "get", "Name", "/value"])
        for line in out.splitlines():
            if "Name=" in line:
                return line.split("=", 1)[-1].strip()

    return platform.processor() or "unknown"


def detect_hardware() -> HardwareProfile:
    """Auto-detect GPU, RAM, and CPU specs for this machine.

    Tries multiple detection strategies in order so the module works on any
    system — from a laptop with no GPU to a workstation with a 24 GB card.

    Detection order for VRAM:
      NVIDIA:
        1a. pynvml Python library (most reliable, works inside containers)
        1b. nvidia-smi at 8+ common filesystem paths (Linux/Windows/WSL)
        1c. /proc/driver/nvidia/gpus/*/information (loaded-driver read)
        1d. PCI sysfs BAR sizes for vendor 0x10de (no driver tools needed)
        1e. lspci -v BAR size parsing
      AMD:
        2a. /sys/class/drm/card*/device/mem_info_vram_total (no ROCm needed)
        2b. rocm-smi
        2c. lspci -v BAR size parsing
      macOS:
        3a. system_profiler SPDisplaysDataType (discrete GPU VRAM)
        3b. Apple Silicon unified memory estimate (RAM × 0.70)
      Windows:
        4a. wmic win32_VideoController
      Fallback:
        5.  lspci NVIDIA/AMD detection with conservative estimate
        6.  0 GB (genuine CPU-only or virtual machine)

    Virtual GPUs (Microsoft Hyper-V vendor 0x1414, VMware, etc.) are
    intentionally skipped — they do not provide real VRAM.

    When no GPU is found the CPU inference budget is derived from RAM:
      cpu_inference_gb = min(ram_gb * 0.5, 16)
    This lets Ollama CPU-mode routing use quantized models up to that size.
    """
    # GPU / VRAM
    vram_gb, gpu_name, gpu_vendor = 0.0, "CPU only", "none"

    # ── NVIDIA ─────────────────────────────────────────────────────────────────
    v, n = _detect_vram_nvidia()
    if v > 0:
        vram_gb, gpu_name, gpu_vendor = v, n, "nvidia"

    # ── AMD ────────────────────────────────────────────────────────────────────
    if vram_gb == 0.0:
        v, n = _detect_vram_amd()
        if v > 0:
            vram_gb, gpu_name, gpu_vendor = v, n, "amd"

    # ── macOS (discrete + Apple Silicon) ──────────────────────────────────────
    if vram_gb == 0.0:
        v, n = _detect_vram_apple()
        if v > 0:
            vram_gb, gpu_name, gpu_vendor = v, n, "apple"

    # ── Windows wmic ──────────────────────────────────────────────────────────
    if vram_gb == 0.0 and platform.system() == "Windows":
        v, n = _detect_vram_windows_wmic()
        if v > 0:
            vram_gb, gpu_name, gpu_vendor = v, n, "unknown"

    # ── Linux lspci fallback (any vendor not yet detected) ────────────────────
    if vram_gb == 0.0 and platform.system() == "Linux":
        lspci_out = _run(["lspci"])
        for line in lspci_out.splitlines():
            low = line.lower()
            if not any(k in low for k in ("vga", "display", "3d controller")):
                continue
            # Skip known virtual / software renderers
            if "microsoft" in low or "vmware" in low or "virtualbox" in low or "hyper-v" in low:
                continue
            if "nvidia" in low:
                gpu_name   = line.split(":", 2)[-1].strip()
                gpu_vendor = "nvidia"
                vram_gb    = _DEFAULT_DISCRETE_GPU_VRAM_GB
                break
            if "amd" in low or "ati" in low:
                gpu_name   = line.split(":", 2)[-1].strip()
                gpu_vendor = "amd"
                vram_gb    = _DEFAULT_DISCRETE_GPU_VRAM_GB
                break
            if "intel" in low:
                gpu_name   = line.split(":", 2)[-1].strip()
                gpu_vendor = "intel"
                vram_gb    = _DEFAULT_INTEL_VRAM_GB
                break

    # RAM + CPU
    ram_gb    = _detect_ram_gb()
    cpu_name  = _detect_cpu_name()
    cpu_cores = os.cpu_count() or 1
    os_name   = f"{platform.system()} {platform.release()} {platform.machine()}".strip()

    # When no GPU is detected, compute a CPU inference budget from RAM so that
    # Ollama CPU-mode routing still works (Ollama maps quantized models to RAM).
    # Use _CPU_INFERENCE_RAM_FRACTION of RAM, capped at _CPU_INFERENCE_MAX_GB.
    if vram_gb == 0.0 and ram_gb > 0:
        cpu_inference_gb = round(min(ram_gb * _CPU_INFERENCE_RAM_FRACTION, _CPU_INFERENCE_MAX_GB), 2)
        gpu_name   = f"CPU only ({ram_gb:.0f} GB RAM)"
        gpu_vendor = "none"
        vram_gb    = cpu_inference_gb

    return HardwareProfile(
        gpu_name   = gpu_name,
        gpu_vendor = gpu_vendor,
        vram_gb    = vram_gb,
        ram_gb     = ram_gb,
        cpu_cores  = cpu_cores,
        cpu_name   = cpu_name,
        os_name    = os_name,
        detection  = "auto",
    )


# ── Module-level hardware profile (detected once at import) ───────────────────
# Use hardware_profile() to access; direct callers can also read _HW.
_HW: HardwareProfile = detect_hardware()

# Track whether the caller explicitly set TURBO_VRAM_BUDGET_GB
_VRAM_ENV_OVERRIDE: bool = bool(os.environ.get("TURBO_VRAM_BUDGET_GB", "").strip())


def hardware_profile() -> HardwareProfile:
    """Return the detected hardware profile for this machine.

    The profile is detected once at import time.  Call detect_hardware() to
    refresh it (e.g. after hot-plugging a GPU — rare but possible).
    """
    return _HW


# ── Hardware-adaptive VRAM budget ─────────────────────────────────────────────
def _compute_vram_budget() -> float:
    """Return the effective VRAM budget in GB.

    Priority:
      1. TURBO_VRAM_BUDGET_GB env var (explicit override)
      2. Detected GPU VRAM × 0.85 safety headroom
      3. 0.0 (CPU-only — model router will always use cloud/NIM)
    """
    env_val = os.environ.get("TURBO_VRAM_BUDGET_GB", "").strip()
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    if _HW.vram_gb > 0:
        return round(_HW.vram_gb * 0.85, 2)
    return 0.0


VRAM_BUDGET_GB: float = _compute_vram_budget()

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

# ── Offline mode — forces local-only providers and maximum quantization ────────
_offline_mode: bool = os.environ.get("TURBO_OFFLINE", "0").strip() in ("1", "true", "yes")


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
# Offline mode management
# ──────────────────────────────────────────────────────────────────────────────

def is_offline_mode() -> bool:
    """Return True when offline mode is active (no cloud providers, max quantization)."""
    return _offline_mode


def set_offline_mode(offline: bool) -> None:
    """Enable or disable offline mode.

    In offline mode:
      • All cloud AI providers (NVIDIA NIM, Anthropic, OpenAI) are disabled.
      • Quantization is forced to Q4_K_M (minimum) to reduce RAM usage.
      • Context window is reduced to stay within local memory limits.
      • Disk offload hints are enabled for models that exceed VRAM budget.
    """
    global _offline_mode
    _offline_mode = bool(offline)
    logger.info("TurboQuant offline mode %s", "ENABLED" if _offline_mode else "DISABLED")


# ──────────────────────────────────────────────────────────────────────────────
# Quant config JSON — persisted user preferences
# ──────────────────────────────────────────────────────────────────────────────

def load_quant_config() -> dict:
    """Load the persisted quantization config from disk.

    Returns the default config merged with whatever is saved on disk.
    Never raises — falls back to defaults on any read/parse error.
    """
    cfg = dict(_DEFAULT_QUANT_CONFIG)
    try:
        if QUANT_CONFIG_FILE.exists():
            with QUANT_CONFIG_FILE.open("r", encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                cfg.update(saved)
    except Exception as exc:
        logger.warning("turbo_quant: could not load quant config — %s", exc)
    return cfg


def save_quant_config(config: dict) -> None:
    """Persist the quantization config to disk.

    Only known keys (from _DEFAULT_QUANT_CONFIG) are saved.
    Applies mode and offline settings immediately to the running process.
    """
    clean: dict = {}
    for key in _DEFAULT_QUANT_CONFIG:
        if key in config:
            clean[key] = config[key]
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with QUANT_CONFIG_FILE.open("w", encoding="utf-8") as fh:
            json.dump(clean, fh, indent=2)
        logger.info("turbo_quant: quant config saved to %s", QUANT_CONFIG_FILE)
    except Exception as exc:
        logger.warning("turbo_quant: could not save quant config — %s", exc)

    # Apply live settings
    if "mode" in clean:
        try:
            set_mode(clean["mode"])
        except ValueError:
            pass
    if "offline" in clean:
        set_offline_mode(bool(clean["offline"]))


def get_quant_config() -> dict:
    """Return the active quantization config, merging disk config with live state.

    The returned dict always includes the current in-process ``mode`` and
    ``offline`` values, which may differ from what is saved on disk if
    ``set_mode()`` or ``set_offline_mode()`` were called at runtime.
    """
    cfg = load_quant_config()
    cfg["mode"]    = get_mode().lower()
    cfg["offline"] = is_offline_mode()
    return cfg


# ──────────────────────────────────────────────────────────────────────────────
# Smart quantization selector
# ──────────────────────────────────────────────────────────────────────────────

def select_quant(gpu_vram_gb: Optional[float] = None, ram_gb: Optional[float] = None) -> str:
    """Return the optimal quantization level for the given hardware budget.

    Uses the detected hardware profile when arguments are omitted.
    Offline mode forces Q4_K_M regardless of available VRAM.

    Args:
        gpu_vram_gb: Available GPU VRAM in GB (auto-detected when None).
        ram_gb:      Available system RAM in GB (auto-detected when None).

    Returns:
        One of QUANT_4BIT, QUANT_5BIT, QUANT_8BIT.
    """
    if _offline_mode:
        return QUANT_4BIT

    vram = gpu_vram_gb if gpu_vram_gb is not None else _HW.vram_gb
    if vram < 6:
        return QUANT_4BIT
    elif vram < 10:
        return QUANT_5BIT
    else:
        return QUANT_8BIT


# ──────────────────────────────────────────────────────────────────────────────
# Disk offload configuration
# ──────────────────────────────────────────────────────────────────────────────

def disk_offload_config(
    params_b: float,
    quant: Optional[str] = None,
    offload_dir: Optional[str] = None,
) -> dict:
    """Return disk-offload configuration for running a large model with limited VRAM.

    Disk offloading streams model layers from disk (or RAM) to the GPU one at a
    time (AirLLM / llama.cpp --mmap style), enabling models that are much larger
    than the VRAM budget.

    Args:
        params_b:    Model size in billions of parameters.
        quant:       Quantization level (auto-selected when None).
        offload_dir: Directory to use for disk-paged layers
                     (defaults to ~/.ai-employee/model_cache).

    Returns:
        Dict with keys: enabled, quant, vram_est_gb, offload_dir,
        gpu_layers_suggested, disk_paging, airllm_recommended, notes.
    """
    if quant is None:
        quant = select_quant()
    vram_est  = vram_estimate_gb(params_b, quant)
    offload   = offload_dir or str(AI_HOME / "model_cache")
    needs_off = vram_est > VRAM_BUDGET_GB

    # Estimate how many layers fit in VRAM.
    # Rough heuristic: 1 GB ≈ 1 / _VRAM_PER_BPARAM[quant] layers per billion params.
    # We approximate total transformer layers as 4 × params_b for typical models.
    total_layers_est = max(1, int(params_b * 4))
    layers_per_gb    = 1.0 / max(0.01, _VRAM_PER_BPARAM.get(quant, 0.58))
    gpu_layers       = int(min(total_layers_est, max(0, VRAM_BUDGET_GB * layers_per_gb)))

    notes: list[str] = []
    if needs_off:
        notes.append(
            f"Model requires ~{vram_est:.1f} GB but budget is {VRAM_BUDGET_GB:.1f} GB — "
            "disk/RAM offload is required."
        )
    if _offline_mode:
        notes.append("Offline mode active — cloud providers disabled.")
    if gpu_layers == 0:
        notes.append("No GPU layers available; running fully on CPU/disk.")

    return {
        "enabled":            needs_off or _offline_mode,
        "quant":              quant,
        "vram_est_gb":        round(vram_est, 2),
        "budget_gb":          round(VRAM_BUDGET_GB, 2),
        "offload_dir":        offload,
        "gpu_layers_suggested": gpu_layers,
        "disk_paging":        needs_off,
        "airllm_recommended": params_b > 13,
        "ollama_cmd_hint": (
            f"ollama run {_MODEL_CATALOGUE.get('tiny_money', {}).get('model', 'llama3.2:3b-instruct-q4_K_M')} "
            f"--gpu-layers {gpu_layers}"
        ),
        "notes":              notes,
    }

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
    directly (no hardware dependency required at call time).
    """
    with _loaded_lock:
        used = sum(_loaded_models.values())
    return {
        "budget_gb":     VRAM_BUDGET_GB,
        "used_est_gb":   round(used, 2),
        "free_est_gb":   round(max(0.0, VRAM_BUDGET_GB - used), 2),
        "loaded_models": dict(_loaded_models),
        "gpu_name":      _HW.gpu_name,
        "gpu_vendor":    _HW.gpu_vendor,
        "detected_vram_gb": _HW.vram_gb,
        "ram_gb":        _HW.ram_gb,
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

    Uses the detected hardware profile to tailor advice to the current machine.
    No hardware calls are made at call time — uses the profile detected at import.
    """
    tips = []
    use_flash_attn = False
    use_onnx       = False
    hw = _HW

    if provider == "ollama":
        if hw.gpu_vendor == "nvidia":
            tips.append(f"Ollama uses llama.cpp with cuBLAS on your {hw.gpu_name} ({hw.vram_gb:.1f} GB VRAM).")
        elif hw.gpu_vendor == "amd":
            tips.append(f"Ollama uses llama.cpp with ROCm on your {hw.gpu_name} ({hw.vram_gb:.1f} GB VRAM).")
        elif hw.gpu_vendor == "apple":
            tips.append(f"Ollama uses Metal on your {hw.gpu_name} — Metal Performance Shaders auto-enabled.")
        elif hw.gpu_vendor in ("none", "unknown") and hw.ram_gb > 0:
            tips.append(
                f"No dedicated GPU detected — Ollama running in CPU mode "
                f"({hw.cpu_cores} cores, {hw.ram_gb:.0f} GB RAM). "
                "Expect slower inference; use small Q4_K_M models for best speed."
            )
        else:
            tips.append(f"Ollama uses llama.cpp with GPU layers on your {hw.gpu_name}.")
        if params_b >= 7:
            use_flash_attn = True
            tips.append("Enable Flash Attention: set OLLAMA_FLASH_ATTN=1 in .env.")
        if quant in (QUANT_4BIT, QUANT_5BIT) and hw.vram_gb > 0:
            tips.append(
                f"Q4_K_M / Q5_K_M GGUF recommended for your {hw.vram_gb:.1f} GB budget — "
                "best size/quality tradeoff."
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

    # KV cache optimisation hints
    kv_cache_tips: list[str] = []
    if provider == "ollama":
        kv_cache_tips.append(
            "Set OLLAMA_KV_CACHE_TYPE=q8_0 in .env to halve KV cache VRAM (minimal quality loss)."
        )
        if params_b >= 7:
            kv_cache_tips.append(
                "For large models use OLLAMA_NUM_CTX=2048 to cap context and reduce KV cache size."
            )
    elif provider in ("nvidia_nim", "openai", "anthropic"):
        kv_cache_tips.append("Cloud provider manages KV cache server-side.")

    if _offline_mode:
        kv_cache_tips.append(
            "Offline mode: context limit auto-reduced to 512 tokens to minimise RAM usage."
        )

    return {
        "flash_attention":    use_flash_attn,
        "onnx_recommended":   use_onnx,
        "batch_supported":    provider == "ollama",
        "kv_cache_tips":      kv_cache_tips,
        "tips":               tips,
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

    # Offline mode: force local provider and tightest available quantization
    if _offline_mode and spec["provider"] != "ollama":
        logger.info(
            "TurboQuant offline mode — overriding provider=%s → ollama, "
            "catalogue=%s → tiny_money",
            spec["provider"], catalogue_key,
        )
        money_spec = _MODEL_CATALOGUE[money_key]
        spec       = money_spec
        params_b   = spec["params_b"]
        quant      = QUANT_4BIT
        vram_est   = vram_estimate_gb(params_b, quant)
        catalogue_key = money_key

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
        + (", offline=True" if _offline_mode else "")
    )

    # Offline mode: reduce context to stay within local memory limits
    max_tokens = spec["max_tokens"]
    if _offline_mode:
        max_tokens = min(max_tokens, 512)

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
        max_tokens  = max_tokens,
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
    Automatically adapts to the detected GPU VRAM of this machine.

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
    gpu_label = _HW.gpu_name if _HW.gpu_name != "CPU only" else "this system"

    if params_b >= 30 or (VRAM_BUDGET_GB > 0 and vram_4bit > VRAM_BUDGET_GB):
        fmt   = QUANT_GPTQ
        tag   = ""
        rationale = (
            f"{params_b:.0f}B parameter model exceeds local VRAM budget ({VRAM_BUDGET_GB:.1f} GB) — "
            "recommend GPTQ/AWQ via NVIDIA NIM or cloud endpoint."
        )
        pull_cmd = f"# Model too large for local VRAM — use NVIDIA NIM or cloud API"
    elif vram_4bit <= VRAM_BUDGET_GB * 0.85:
        fmt   = QUANT_4BIT
        tag   = "q4_K_M"
        rationale = (
            f"Q4_K_M uses ~{vram_4bit:.1f} GB VRAM — fits comfortably on {gpu_label}. "
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
            f"Even Q8_0 ({vram_8bit:.1f} GB) exceeds VRAM budget ({VRAM_BUDGET_GB:.1f} GB). "
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

    # Hardware detection
    hw = hardware_profile()
    assert isinstance(hw, HardwareProfile), "hardware_profile() failed"
    assert hw.cpu_cores >= 1,  "cpu_cores must be ≥ 1"
    assert hw.ram_gb >= 0,     "ram_gb must be ≥ 0"
    assert hw.vram_gb >= 0,    "vram_gb must be ≥ 0"
    assert hw.gpu_vendor in ("nvidia", "amd", "apple", "intel", "unknown", "none"), \
        f"unexpected gpu_vendor: {hw.gpu_vendor}"
    print(f"  hardware: gpu={hw.gpu_name} vram={hw.vram_gb:.1f}GB "
          f"ram={hw.ram_gb:.1f}GB cpu={hw.cpu_cores}×{hw.cpu_name[:30]}  ✓")

    # VRAM budget is derived from hardware
    assert VRAM_BUDGET_GB >= 0, f"VRAM_BUDGET_GB should be ≥ 0, got {VRAM_BUDGET_GB}"
    print(f"  VRAM_BUDGET_GB={VRAM_BUDGET_GB:.2f} GB (auto-detected)  ✓")

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
    assert cfg_money.provider == "ollama",     f"money tier should be ollama, got {cfg_money.provider}"
    assert cfg_power.provider == "nvidia_nim", f"power tier reasoning should be nvidia_nim, got {cfg_power.provider}"
    assert cfg_money.params_b <= cfg_power.params_b or cfg_power.params_b == 0, "power should be larger"
    print(f"  money  model={cfg_money.model}  quant={cfg_money.quant}  ✓")
    print(f"  power  model={cfg_power.model}  quant={cfg_power.quant}  ✓")

    # VRAM estimate
    est = vram_estimate_gb(7.0, QUANT_4BIT)
    assert 0 < est < 10, f"VRAM estimate out of range: {est}"
    print(f"  VRAM estimate 7B Q4_K_M = {est:.2f} GB  ✓")

    # Memory status — must include hardware fields
    register_loaded_model("test-model", 3.0)
    status = memory_status()
    assert status["used_est_gb"] == 3.0, f"memory tracking failed: {status}"
    assert "gpu_name" in status,         "memory_status missing gpu_name"
    assert "ram_gb"   in status,         "memory_status missing ram_gb"
    unregister_model("test-model")
    assert memory_status()["used_est_gb"] == 0.0, "unregister failed"
    print("  memory tracking  ✓")

    # Suggest acceleration
    accel = suggest_acceleration(7.0, "ollama", QUANT_4BIT)
    assert accel["flash_attention"] is True
    assert accel["batch_supported"] is True
    print("  acceleration hints  ✓")

    # Quantization recommendation — result depends on detected VRAM
    rec = recommend_quant_format(7.0)
    assert rec["format"] in (QUANT_4BIT, QUANT_5BIT, QUANT_8BIT, QUANT_GPTQ, QUANT_FP16), \
        f"unexpected quant format: {rec['format']}"
    print(f"  recommend_quant 7B = {rec['format']}  vram_budget={VRAM_BUDGET_GB:.1f}GB  ✓")

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
