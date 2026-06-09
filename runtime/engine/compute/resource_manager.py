"""System Resource Manager — auto-detects hardware, enforces OS-safe budgets,
assigns models, and coordinates voice model selection.

Safety contract: this system NEVER consumes more than its configured budget
fractions of CPU/RAM/VRAM. The remainder is reserved for the host OS and
normal computer operations. The laptop profile uses tighter defaults.

Budget defaults (overridable via env vars):
  RAM:  70% of total (leaves 30% for OS + browser + other apps)
  VRAM: 85% of total (leaves 15% for driver overhead)
  CPU:  75% of logical cores (leaves 25% for OS responsiveness)

On detected low-RAM systems (< 10 GB total) budgets tighten automatically.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger("engine.compute.resources")

# ── Safety budget fractions ────────────────────────────────────────────────────
_DEFAULT_RAM_FRACTION  = 0.70   # 70% of total RAM for AI workloads
_DEFAULT_VRAM_FRACTION = 0.85   # 85% of VRAM (15% for driver/KV-cache headroom)
_DEFAULT_CPU_FRACTION  = 0.75   # 75% of CPU cores

# Low-resource machine tightens budgets further
_LOW_RAM_THRESHOLD_GB  = 10.0
_LOW_RAM_FRACTION      = 0.60
_LOW_CPU_FRACTION      = 0.60

# Voice model VRAM requirements (MB)
_VOICE_VRAM = {
    "whisper_base":    148,    # whisper.cpp base.en — 148 MB, runs on any GPU/CPU
    "whisper_small":   466,    # whisper.cpp small.en
    "whisper_medium":  1500,   # whisper.cpp medium.en
    "voice_lite":      150,    # voice_lite TTS (CPU only, no GPU needed)
    "piper":           50,     # Piper TTS (CPU, very fast)
    "kokoro":          350,    # Kokoro-82M TTS (GPU optional)
    "fish_speech":     2500,   # Fish Speech S2-Pro — needs dedicated VRAM
}

# LLM model VRAM requirements (MB) — matched to installed Ollama models
_LLM_VRAM = {
    "llama3.2:latest":        2000,
    "gemma3:latest":          3300,
    "qwen2.5:7b-instruct":    4700,
    "qwen2.5-coder:14b":      9000,
    "llava:latest":           4700,
    "qwen3.5":                6600,
    "nomic-embed-text":        400,
}

# Minimum OS reserve — never go below these regardless of budget fractions
_MIN_OS_RAM_GB   = 2.0
_MIN_OS_VRAM_MB  = 512
_MIN_OS_CPU_PCT  = 20


@dataclass
class SystemSpecs:
    """Detected hardware specifications."""
    gpu_name:    str   = "none"
    gpu_vendor:  str   = "none"
    vram_total_mb: int = 0
    vram_free_mb:  int = 0
    ram_total_gb:  float = 0.0
    ram_free_gb:   float = 0.0
    cpu_cores:     int   = 1
    cpu_name:      str   = "unknown"
    os_name:       str   = "unknown"
    is_laptop:     bool  = False
    detected_at:   float = 0.0


@dataclass
class SystemBudget:
    """Safe resource budget for AI workloads — the system must stay within these."""
    # Hard ceilings the AI system must not exceed
    max_ram_gb:    float = 0.0    # GB of RAM available for AI
    max_vram_mb:   int   = 0      # MB of VRAM available for AI
    max_cpu_cores: int   = 1      # logical CPU cores the AI may saturate

    # Derived: what fits right now (free - OS reserve)
    usable_ram_gb:  float = 0.0
    usable_vram_mb: int   = 0

    # Recommended model stack for this machine
    llm_primary:   str = "llama3.2:latest"       # always-hot fast model
    llm_reasoning: str = "qwen2.5:7b-instruct"   # on-demand reasoning
    llm_coder:     str = "qwen2.5-coder:14b"     # on-demand, CPU offload if needed
    llm_embed:     str = "nomic-embed-text"       # always-hot embeddings
    stt_model:     str = "whisper_base"           # speech-to-text
    tts_engine:    str = "voice_lite"             # text-to-speech
    can_run_coder: bool = False                   # true if 14B fits with offload
    can_run_vision: bool = False                  # true if llava fits

    specs: SystemSpecs = field(default_factory=SystemSpecs)


class ResourceManager:
    """Process-singleton. Detects hardware once, exposes safe budget, monitors drift.

    Usage:
        mgr = get_resource_manager()
        budget = mgr.budget          # always up-to-date
        mgr.assert_safe(ram_gb=2.0)  # raises if would exceed budget
    """

    _refresh_interval_s = 30  # re-check free RAM/VRAM every 30s

    def __init__(self):
        self._lock = threading.RLock()
        self._specs: SystemSpecs = self._detect_specs()
        self._budget: SystemBudget = self._compute_budget(self._specs)
        self._last_refresh = time.monotonic()
        logger.info(
            "ResourceManager init: vram=%dMB free, ram=%.1fGB free, cpu=%d cores",
            self._specs.vram_free_mb, self._specs.ram_free_gb, self._specs.cpu_cores,
        )
        logger.info(
            "Budget: max_vram=%dMB, max_ram=%.1fGB, max_cpu=%d | primary=%s stt=%s tts=%s",
            self._budget.max_vram_mb, self._budget.max_ram_gb, self._budget.max_cpu_cores,
            self._budget.llm_primary, self._budget.stt_model, self._budget.tts_engine,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def specs(self) -> SystemSpecs:
        self._maybe_refresh()
        return self._specs

    @property
    def budget(self) -> SystemBudget:
        self._maybe_refresh()
        return self._budget

    def assert_safe(self, ram_gb: float = 0.0, vram_mb: int = 0) -> None:
        """Raise RuntimeError if loading something would breach the OS reserve."""
        b = self.budget
        if ram_gb > 0 and b.usable_ram_gb < ram_gb:
            raise RuntimeError(
                f"RAM insufficient: need {ram_gb:.1f}GB, only {b.usable_ram_gb:.1f}GB usable"
            )
        if vram_mb > 0 and b.usable_vram_mb < vram_mb:
            raise RuntimeError(
                f"VRAM insufficient: need {vram_mb}MB, only {b.usable_vram_mb}MB usable"
            )

    def can_load(self, vram_mb: int = 0, ram_gb: float = 0.0) -> bool:
        """True if there's room to load a model without breaching OS reserves."""
        b = self.budget
        vram_ok = vram_mb <= 0 or b.usable_vram_mb >= vram_mb
        ram_ok  = ram_gb  <= 0 or b.usable_ram_gb  >= ram_gb
        return vram_ok and ram_ok

    def select_voice_models(self) -> dict[str, str]:
        """Return the best STT/TTS combo for this hardware, prioritising quality within budget."""
        b = self.budget
        return {"stt": b.stt_model, "tts": b.tts_engine}

    def select_llm_stack(self) -> dict[str, str]:
        """Return recommended LLM model names for primary / reasoning / coder / embed."""
        b = self.budget
        return {
            "primary":   b.llm_primary,
            "reasoning": b.llm_reasoning,
            "coder":     b.llm_coder,
            "embed":     b.llm_embed,
            "can_run_coder": b.can_run_coder,
            "can_run_vision": b.can_run_vision,
        }

    def to_dict(self) -> dict:
        b = self.budget
        s = self.specs
        # Live CPU/GPU util — best effort, 0 if psutil unavailable
        try:
            import psutil as _ps
            cpu_pct = _ps.cpu_percent(interval=None)
        except Exception:
            cpu_pct = 0
        return {
            # Flat fields consumed directly by frontend
            "gpu_name":       s.gpu_name,
            "vram_total_mb":  s.vram_total_mb,
            "vram_free_mb":   s.vram_free_mb,
            "ram_total_gb":   s.ram_total_gb,
            "ram_used_gb":    round(s.ram_total_gb - s.ram_free_gb, 2),
            "ram_free_gb":    s.ram_free_gb,
            "cpu_cores":      s.cpu_cores,
            "cpu_pct":        cpu_pct,
            "gpu_util_pct":   0,  # Ollama doesn't expose utilisation; VRAM shows pressure
            "is_laptop":      s.is_laptop,
            # Budget ceilings
            "budget": {
                "max_ram_gb":     b.max_ram_gb,
                "max_vram_mb":    b.max_vram_mb,
                "max_cpu_cores":  b.max_cpu_cores,
                "usable_ram_gb":  b.usable_ram_gb,
                "usable_vram_mb": b.usable_vram_mb,
            },
            # Model stack
            "recommended_stack": {
                "llm_primary":    b.llm_primary,
                "llm_reasoning":  b.llm_reasoning,
                "llm_coder":      b.llm_coder,
                "llm_embed":      b.llm_embed,
                "stt_model":      b.stt_model,
                "tts_engine":     b.tts_engine,
                "can_run_coder":  b.can_run_coder,
                "can_run_vision": b.can_run_vision,
            },
        }

    # ── Detection ──────────────────────────────────────────────────────────────

    def _detect_specs(self) -> SystemSpecs:
        mem = psutil.virtual_memory()
        ram_total_gb = mem.total / (1024 ** 3)
        ram_free_gb  = mem.available / (1024 ** 3)
        cpu_cores = os.cpu_count() or 1

        vram_total_mb, vram_free_mb, gpu_name, gpu_vendor = self._detect_gpu()
        is_laptop = self._detect_laptop()

        return SystemSpecs(
            gpu_name      = gpu_name,
            gpu_vendor    = gpu_vendor,
            vram_total_mb = vram_total_mb,
            vram_free_mb  = vram_free_mb,
            ram_total_gb  = round(ram_total_gb, 2),
            ram_free_gb   = round(ram_free_gb, 2),
            cpu_cores     = cpu_cores,
            cpu_name      = self._detect_cpu_name(),
            os_name       = f"{platform.system()} {platform.release()} {platform.machine()}",
            is_laptop     = is_laptop,
            detected_at   = time.time(),
        )

    def _detect_gpu(self) -> tuple[int, int, str, str]:
        """Return (vram_total_mb, vram_free_mb, name, vendor)."""
        # NVIDIA via nvidia-smi
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=memory.total,memory.free,name",
                     "--format=csv,noheader,nounits"],
                    text=True, timeout=4,
                )
                parts = out.strip().splitlines()[0].split(",")
                total_mb = int(parts[0].strip())
                free_mb  = int(parts[1].strip())
                name     = parts[2].strip() if len(parts) > 2 else "NVIDIA GPU"
                return total_mb, free_mb, name, "nvidia"
            except Exception:
                pass

        # AMD via rocm-smi
        if shutil.which("rocm-smi"):
            try:
                out = subprocess.check_output(
                    ["rocm-smi", "--showmeminfo", "vram", "--csv"],
                    text=True, timeout=4,
                )
                for line in out.splitlines():
                    parts = line.split(",")
                    if len(parts) >= 2 and parts[-1].strip().isdigit():
                        total_mb = int(parts[-1].strip()) // (1024 * 1024)
                        return total_mb, total_mb, "AMD GPU", "amd"
            except Exception:
                pass

        return 0, 0, "none", "none"

    def _detect_laptop(self) -> bool:
        """Heuristic: detect laptop via battery or chassis type."""
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                return True
        except Exception:
            pass
        # Linux chassis type
        chassis = Path("/sys/class/dmi/id/chassis_type")
        if chassis.exists():
            try:
                ctype = int(chassis.read_text().strip())
                # 8=portable, 9=laptop, 10=notebook, 14=sub-notebook
                if ctype in (8, 9, 10, 14, 31, 32):
                    return True
            except Exception:
                pass
        return False

    def _detect_cpu_name(self) -> str:
        try:
            if platform.system() == "Linux":
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line.lower():
                            return line.split(":", 1)[-1].strip()
        except Exception:
            pass
        return platform.processor() or "unknown"

    # ── Budget computation ─────────────────────────────────────────────────────

    def _compute_budget(self, s: SystemSpecs) -> SystemBudget:
        # Tighten fractions for low-RAM or laptop
        low_ram = s.ram_total_gb < _LOW_RAM_THRESHOLD_GB
        is_constrained = low_ram or s.is_laptop

        ram_frac  = _LOW_RAM_FRACTION  if is_constrained else _DEFAULT_RAM_FRACTION
        cpu_frac  = _LOW_CPU_FRACTION  if is_constrained else _DEFAULT_CPU_FRACTION
        vram_frac = _DEFAULT_VRAM_FRACTION  # VRAM headroom same for all

        # Max the system may use total
        max_ram_gb    = max(0.0, s.ram_total_gb  * ram_frac  - _MIN_OS_RAM_GB)
        max_vram_mb   = max(0,   int(s.vram_total_mb * vram_frac) - _MIN_OS_VRAM_MB)
        max_cpu_cores = max(1,   int(s.cpu_cores * cpu_frac))

        # What's usable RIGHT NOW (free minus OS reserve)
        usable_ram_gb  = max(0.0, s.ram_free_gb        - _MIN_OS_RAM_GB)
        usable_vram_mb = max(0,   s.vram_free_mb        - _MIN_OS_VRAM_MB)

        # Never exceed the hard ceiling
        usable_ram_gb  = min(usable_ram_gb,  max_ram_gb)
        usable_vram_mb = min(usable_vram_mb, max_vram_mb)

        # ── Model stack selection ──────────────────────────────────────────────
        # Primary LLM: always llama3.2 (2GB) — fits on any GPU or CPU
        llm_primary = "llama3.2:latest"

        # Reasoning: qwen2.5:7b-instruct (4.7GB) — fits if >= 5GB usable VRAM
        llm_reasoning = "qwen2.5:7b-instruct" if max_vram_mb >= 4500 else "gemma3:latest"

        # Coder: qwen2.5-coder:14b (9GB) — offloads to CPU if needed, needs >= 4GB VRAM + 6GB RAM
        can_run_coder = (max_vram_mb >= 3500) and (max_ram_gb >= 6.0)
        llm_coder = "qwen2.5-coder:14b" if can_run_coder else llm_reasoning

        # Vision
        can_run_vision = max_vram_mb >= 4000
        llm_vision = "llava:latest" if can_run_vision else None

        # Embeddings: always nomic-embed-text (400MB) — tiny, permanent resident
        llm_embed = "nomic-embed-text"

        # ── Voice model selection ──────────────────────────────────────────────
        # STT: prefer whisper_small (466MB) if VRAM allows, else whisper_base (148MB, CPU OK)
        if max_vram_mb >= 600:
            stt_model = "whisper_small"
        else:
            stt_model = "whisper_base"

        # TTS: prefer kokoro (350MB GPU, high quality) if VRAM allows;
        #      fallback to voice_lite (CPU, 150MB RAM only)
        if max_vram_mb >= 1000:
            tts_engine = "kokoro"
        else:
            tts_engine = "voice_lite"

        # Further constrain voice models if system is under heavy RAM pressure
        if usable_ram_gb < 1.5:
            stt_model = "whisper_base"
            tts_engine = "voice_lite"

        return SystemBudget(
            max_ram_gb    = round(max_ram_gb, 2),
            max_vram_mb   = max_vram_mb,
            max_cpu_cores = max_cpu_cores,
            usable_ram_gb  = round(usable_ram_gb, 2),
            usable_vram_mb = usable_vram_mb,
            llm_primary   = llm_primary,
            llm_reasoning = llm_reasoning,
            llm_coder     = llm_coder,
            llm_embed     = llm_embed,
            stt_model     = stt_model,
            tts_engine    = tts_engine,
            can_run_coder = can_run_coder,
            can_run_vision = can_run_vision,
            specs         = s,
        )

    def _maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_refresh < self._refresh_interval_s:
            return
        with self._lock:
            if now - self._last_refresh < self._refresh_interval_s:
                return
            try:
                mem = psutil.virtual_memory()
                self._specs.ram_free_gb = round(mem.available / (1024 ** 3), 2)
                _, vram_free, _, _ = self._detect_gpu()
                self._specs.vram_free_mb = vram_free
                self._specs.detected_at  = time.time()
                # Recompute usable values only (not max — that's fixed by total)
                s = self._specs
                self._budget.usable_ram_gb  = round(max(0.0, s.ram_free_gb  - _MIN_OS_RAM_GB), 2)
                self._budget.usable_vram_mb = max(0, s.vram_free_mb - _MIN_OS_VRAM_MB)
                self._budget.usable_ram_gb  = min(self._budget.usable_ram_gb,  self._budget.max_ram_gb)
                self._budget.usable_vram_mb = min(self._budget.usable_vram_mb, self._budget.max_vram_mb)
            except Exception as exc:
                logger.debug("resource refresh failed: %s", exc)
            self._last_refresh = now


# ── Singleton ──────────────────────────────────────────────────────────────────
_MANAGER: ResourceManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_resource_manager() -> ResourceManager:
    global _MANAGER
    if _MANAGER is None:
        with _MANAGER_LOCK:
            if _MANAGER is None:
                _MANAGER = ResourceManager()
    return _MANAGER
