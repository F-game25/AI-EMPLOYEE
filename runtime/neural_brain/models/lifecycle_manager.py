"""Model Lifecycle Manager — VRAM-aware loading, unloading, and quant selection.

The host GPU is finite (e.g. 8 GB). Loading LCM (~4 GB) + SAM (~1 GB) + a 7B VLM
(~5 GB) at once starves the GPU and crashes runners. This manager enforces:

  • single heavy load at a time (lock) — no two big models race for VRAM
  • a VRAM check before every heavy load; evict idle heavy models to make room
  • idle eviction — heavy models unload after TTL; SLM + embeddings stay resident
  • quant selection — pick a GGUF quant tier that fits free VRAM (Q8→Q2) or
    signal "needs remote" instead of OOM-crashing

Providers register an unloader so the manager can free real memory:
  • diffusers / SAM  → clear the cached pipeline + torch.cuda.empty_cache()
  • ollama           → ollama.generate(keep_alive=0) drops the model from VRAM

This is the single gate every local heavy load should pass through. It never raises
— it returns a structured plan/result so callers degrade instead of crashing.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Heavy archs compete for VRAM and load on demand. SLM + MLM(embeddings) are light
# and may stay resident.
HEAVY_ARCHS = {"LLM", "VLM", "LCM", "SAM", "MoE", "LAM"}
RESIDENT_ARCHS = {"SLM", "MLM"}

# Rough VRAM footprints (MB) used for admission control / quant planning.
_EST_VRAM_MB = {
    "LCM": 4200,   # SD1.5-class diffusion in fp16
    "SAM": 1100,   # ViT-B
    "VLM": 5200,   # 7B vision in Q4
    "LLM": 9000,   # 14B in Q4 (qwen2.5-coder:14b)
    "MoE": 5200,
    "LAM": 9000,
    "SLM": 2200,
    "MLM": 400,
}

# GGUF quant ladder: (name, bits-per-weight-ish multiplier, quality, speed).
# bytes ≈ params * bpw / 8. Used to pick the largest quant that fits free VRAM.
_QUANT_LADDER = [
    ("Q8_0",  8.5, "highest", "slow"),
    ("Q6_K",  6.6, "high",    "medium"),
    ("Q5_K_M", 5.7, "high",   "medium"),
    ("Q4_K_M", 4.8, "balanced", "fast"),
    ("Q3_K_M", 3.9, "reduced", "fast"),
    ("Q2_K",  3.0, "emergency", "fastest"),
]


@dataclass
class ModelEntry:
    model_id: str
    arch: str
    provider: str
    est_vram_mb: int = 0
    loaded: bool = False
    last_used: float = 0.0
    load_ms: float = 0.0
    loads: int = 0
    last_error: str | None = None
    quant: str | None = None
    unloader: object = field(default=None, repr=False)  # callable | None


def _free_vram_mb() -> int | None:
    """Free GPU VRAM in MB via nvidia-smi, or None if no GPU."""
    import shutil
    import subprocess
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True, timeout=4)
        return int(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


def _total_vram_mb() -> int | None:
    import shutil
    import subprocess
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True, timeout=4)
        return int(out.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return None


class ModelLifecycleManager:
    """Process-wide singleton. Thread-safe."""

    def __init__(self, idle_ttl_s: int = 600):
        self._reg: dict[str, ModelEntry] = {}
        self._lock = threading.RLock()
        self._heavy_load_lock = threading.Lock()  # serialize heavy loads
        self.idle_ttl_s = idle_ttl_s

    # ── registration ────────────────────────────────────────────────────────
    def register(self, model_id: str, arch: str, provider: str, *,
                 est_vram_mb: int | None = None, unloader=None) -> ModelEntry:
        with self._lock:
            e = self._reg.get(model_id)
            if e is None:
                e = ModelEntry(model_id=model_id, arch=arch, provider=provider,
                               est_vram_mb=est_vram_mb or _EST_VRAM_MB.get(arch, 1500))
                self._reg[model_id] = e
            else:
                e.arch, e.provider = arch, provider
                if est_vram_mb:
                    e.est_vram_mb = est_vram_mb
            if unloader is not None:
                e.unloader = unloader
            return e

    def mark_loaded(self, model_id: str, *, load_ms: float = 0.0, quant: str | None = None):
        with self._lock:
            e = self._reg.get(model_id)
            if e:
                e.loaded = True
                e.last_used = time.time()
                e.load_ms = load_ms or e.load_ms
                e.loads += 1
                e.last_error = None
                if quant:
                    e.quant = quant

    def touch(self, model_id: str):
        with self._lock:
            if e := self._reg.get(model_id):
                e.last_used = time.time()

    # ── admission control ─────────────────────────────────────────────────────
    def ensure_room(self, arch: str, need_mb: int | None = None) -> dict:
        """Evict idle heavy models until `need_mb` fits in free VRAM.

        Returns a plan dict: {fits, free_mb, need_mb, evicted, recommend_remote}.
        """
        need = need_mb or _EST_VRAM_MB.get(arch, 1500)
        free = _free_vram_mb()
        total = _total_vram_mb()
        if free is None:  # CPU-only host — no VRAM admission needed
            return {"fits": True, "free_mb": None, "need_mb": need, "evicted": [],
                    "recommend_remote": False, "device": "cpu"}

        evicted = []
        if free < need:
            # Evict idle heavy models (oldest first), never resident archs.
            with self._lock:
                candidates = sorted(
                    (e for e in self._reg.values()
                     if e.loaded and e.arch in HEAVY_ARCHS and e.arch != arch),
                    key=lambda e: e.last_used)
            for e in candidates:
                self.unload(e.model_id)
                evicted.append(e.model_id)
                free = _free_vram_mb() or free
                if free >= need:
                    break

        fits = free >= need
        # If even a full GPU can't hold it, recommend remote compute.
        recommend_remote = (total is not None and total < need)
        return {"fits": fits, "free_mb": free, "need_mb": need, "total_mb": total,
                "evicted": evicted, "recommend_remote": recommend_remote, "device": "cuda"}

    # ── quant selection ────────────────────────────────────────────────────────
    def select_quant(self, params_b: float, *, free_mb: int | None = None,
                     dev_override: bool = False) -> dict:
        """Pick the largest GGUF quant whose weights fit in free VRAM.

        params_b = model size in billions. Returns {quant, est_vram_mb, quality,
        speed, fits, recommend_remote, reason}. FP16 is blocked unless dev_override.
        """
        free = free_mb if free_mb is not None else _free_vram_mb()
        # Reserve headroom for KV-cache + activations (~25%).
        budget = int(free * 0.75) if free else None

        if dev_override:
            fp16_mb = int(params_b * 1e9 * 2 / 1e6)
            return {"quant": "FP16", "est_vram_mb": fp16_mb, "quality": "full",
                    "speed": "slow", "fits": budget is None or fp16_mb <= budget,
                    "recommend_remote": False, "reason": "developer override (full precision)"}

        for name, bpw, quality, speed in _QUANT_LADDER:
            est = int(params_b * 1e9 * bpw / 8 / 1e6)
            if budget is None or est <= budget:
                return {"quant": name, "est_vram_mb": est, "quality": quality,
                        "speed": speed, "fits": True, "recommend_remote": False,
                        "reason": f"largest quant fitting {budget}MB budget" if budget else "cpu host"}
        # Nothing fits — emergency quant still too big.
        smallest = _QUANT_LADDER[-1]
        est = int(params_b * 1e9 * smallest[1] / 8 / 1e6)
        return {"quant": smallest[0], "est_vram_mb": est, "quality": smallest[2],
                "speed": smallest[3], "fits": False, "recommend_remote": True,
                "reason": f"even {smallest[0]} ({est}MB) exceeds {budget}MB — use remote compute"}

    # ── load / unload ──────────────────────────────────────────────────────────
    def acquire_heavy(self, arch: str, need_mb: int | None = None) -> dict:
        """Call before a heavy load. Serializes heavy loads + makes VRAM room."""
        if arch not in HEAVY_ARCHS:
            return {"ok": True, "lock": False}
        self._heavy_load_lock.acquire()
        plan = self.ensure_room(arch, need_mb)
        plan["lock"] = True
        plan["ok"] = plan["fits"]
        return plan

    def release_heavy(self):
        if self._heavy_load_lock.locked():
            try:
                self._heavy_load_lock.release()
            except RuntimeError:
                pass

    def unload(self, model_id: str) -> bool:
        with self._lock:
            e = self._reg.get(model_id)
            if not e or not e.loaded:
                return False
        try:
            if callable(e.unloader):
                e.unloader()
            self._empty_cuda_cache()
            with self._lock:
                e.loaded = False
            logger.info("Unloaded model %s (%s)", model_id, e.arch)
            return True
        except Exception as ex:  # noqa: BLE001
            logger.warning("unload %s failed: %s", model_id, ex)
            with self._lock:
                e.last_error = str(ex)
            return False

    def unload_idle(self) -> list[str]:
        now = time.time()
        with self._lock:
            stale = [e.model_id for e in self._reg.values()
                     if e.loaded and e.arch in HEAVY_ARCHS
                     and (now - e.last_used) > self.idle_ttl_s]
        return [m for m in stale if self.unload(m)]

    @staticmethod
    def _empty_cuda_cache():
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    # ── status ─────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        now = time.time()
        with self._lock:
            models = [{
                "model_id": e.model_id, "arch": e.arch, "provider": e.provider,
                "loaded": e.loaded, "est_vram_mb": e.est_vram_mb, "quant": e.quant,
                "load_ms": round(e.load_ms, 1), "loads": e.loads,
                "idle_s": round(now - e.last_used, 1) if e.last_used else None,
                "last_error": e.last_error,
            } for e in self._reg.values()]
        loaded = [m for m in models if m["loaded"]]
        return {
            "free_vram_mb": _free_vram_mb(), "total_vram_mb": _total_vram_mb(),
            "idle_ttl_s": self.idle_ttl_s, "heavy_load_busy": self._heavy_load_lock.locked(),
            "models_loaded": len(loaded), "models_registered": len(models),
            "models": models,
        }


_MANAGER: ModelLifecycleManager | None = None


def get_lifecycle_manager() -> ModelLifecycleManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ModelLifecycleManager()
    return _MANAGER
