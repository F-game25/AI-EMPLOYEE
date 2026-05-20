"""Route requests to the appropriate model architecture.

Upgrades over v1:
- Per-arch blacklist (backed by HealthMonitor)
- Retry with exponential backoff (max 3 attempts per arch)
- Records latency + ok/fail to HealthMonitor after every call
- Emits enriched nb:model_call via EventBus
- route_adaptive() uses performance tracker for weighted selection
"""
from __future__ import annotations

import logging
import time
from typing import Literal

from neural_brain.core.feature_flags import FeatureFlags

logger = logging.getLogger(__name__)

Arch = Literal["LLM", "SLM", "MoE", "VLM", "MLM", "LAM", "LCM", "SAM"]

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.3  # seconds


class ModelArchitectureRouter:
    """Dispatch inference requests to 8 model architectures."""

    ARCHS = ("LLM", "SLM", "MoE", "VLM", "MLM", "LAM", "LCM", "SAM")

    @staticmethod
    def route(arch: Arch, request: dict, *, _attempt: int = 1) -> dict:
        """Route with retry + backoff + health recording."""
        start = time.time()
        flags = FeatureFlags()
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            if attempt > 1:
                time.sleep(_BACKOFF_BASE * (2 ** (attempt - 2)))
            try:
                result = ModelArchitectureRouter._dispatch(arch, request, flags)
                latency_ms = (time.time() - start) * 1000
                result.setdefault("latency_ms", latency_ms)
                result.setdefault("arch", arch)
                ok = result.get("status") != "error"
                ModelArchitectureRouter._record(arch, latency_ms, ok, result.get("provider", arch))
                ModelArchitectureRouter._emit_call(arch, result, latency_ms)
                if ok:
                    return result
                # Status=error but no exception — don't retry disabled arches
                if result.get("status") == "disabled":
                    return result
                last_exc = None  # mark as soft error for retry logic
            except Exception as exc:
                last_exc = exc
                latency_ms = (time.time() - start) * 1000
                ModelArchitectureRouter._record(arch, latency_ms, False, arch)
                if attempt == _MAX_RETRIES:
                    break

        latency_ms = (time.time() - start) * 1000
        error_str = str(last_exc) if last_exc else "max retries exceeded"
        logger.error("route(%s) failed after %d attempts: %s", arch, _MAX_RETRIES, error_str)
        result = {"status": "error", "arch": arch, "error": error_str, "latency_ms": latency_ms}
        ModelArchitectureRouter._emit_call(arch, result, latency_ms)
        return result

    @staticmethod
    def _dispatch(arch: str, request: dict, flags: FeatureFlags) -> dict:
        """Single dispatch attempt — no retry logic here."""
        # Respect privacy mode: block external providers in OFFLINE mode
        provider = request.get("provider", "")
        if provider in ("openrouter", "anthropic", "openai"):
            try:
                from neural_brain.config.privacy_mode import can_use_external_apis
                if not can_use_external_apis():
                    return {
                        "status": "blocked",
                        "arch": arch,
                        "reason": "PRIVACY_MODE=OFFLINE — external API calls disabled",
                        "provider": provider,
                    }
            except Exception:
                pass
        if arch == "LLM":
            from neural_brain.models.llm_backend import route_llm
            return route_llm(request)
        elif arch == "SLM":
            from neural_brain.models.slm_backend import route_slm
            return route_slm(request)
        elif arch == "MoE":
            from neural_brain.models.moe_backend import route_moe
            return route_moe(request)
        elif arch == "VLM":
            from neural_brain.models.vlm_backend import route_vlm
            return route_vlm(request)
        elif arch == "MLM":
            from neural_brain.models.mlm_backend import route_mlm
            return route_mlm(request)
        elif arch == "LAM":
            from neural_brain.models.lam_backend import route_lam
            return route_lam(request)
        elif arch == "LCM":
            if not flags.is_lcm_enabled():
                return {"status": "disabled", "arch": arch, "reason": "LCM disabled (NEURAL_BRAIN_LCM_ENABLED=true)"}
            from neural_brain.models.lcm_backend import route_lcm
            return route_lcm(request)
        elif arch == "SAM":
            if not flags.is_sam_enabled():
                return {"status": "disabled", "arch": arch, "reason": "SAM disabled (NEURAL_BRAIN_SAM_ENABLED=true)"}
            from neural_brain.models.sam_backend import route_sam
            return route_sam(request)
        return {"status": "error", "error": f"Unknown architecture: {arch}"}

    @staticmethod
    def _record(arch: str, latency_ms: float, ok: bool, source: str) -> None:
        try:
            from neural_brain.core.health_monitor import get_health_monitor
            get_health_monitor().record(latency_ms=latency_ms, ok=ok, source=f"model:{arch}:{source}")
        except Exception:
            pass
        try:
            from neural_brain.models.performance_tracker import get_tracker
            get_tracker().record(arch, source, source, latency_ms, "ok" if ok else "error")
        except Exception:
            pass

    @staticmethod
    def _emit_call(arch: str, result: dict, latency_ms: float) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("nb:model_call", source="neural_brain", payload={
                "arch": arch,
                "status": result.get("status"),
                "latency_ms": round(latency_ms, 1),
                "provider": result.get("provider"),
                "error": result.get("error"),
            })
        except Exception:
            pass

    # ── Adaptive routing ──────────────────────────────────────────────────

    @staticmethod
    def route_adaptive(arch: str, request: dict) -> dict:
        """Route to best candidate based on tracked performance + blacklist check."""
        from neural_brain.models.performance_tracker import get_tracker
        from neural_brain.core.health_monitor import get_health_monitor

        tracker = get_tracker()
        monitor = get_health_monitor()
        registry = ModelArchitectureRouter.get_registry()
        raw_candidates: list = registry.get(arch, [])

        candidates: list[dict] = []
        for entry in raw_candidates:
            if isinstance(entry, dict):
                candidates.append(entry)
            elif isinstance(entry, str):
                provider = entry.split(":")[0] if ":" in entry else "ollama"
                candidates.append({"provider": provider, "raw": entry})

        if not candidates:
            return ModelArchitectureRouter.route(arch, request)

        # Filter blacklisted sources
        candidates = [c for c in candidates if not monitor.is_blacklisted(f"model:{arch}:{c.get('provider', '')}")]
        if not candidates:
            candidates = [{"provider": arch, "raw": arch}]  # last resort

        ranked = tracker.rank_options(arch, candidates)
        candidate_count = len(ranked)
        last_error = ""
        _MAX_ADAPTIVE_TRIES = min(candidate_count, 3)  # never try more than 3 even with large registry

        for rank, candidate in enumerate(ranked[:_MAX_ADAPTIVE_TRIES]):
            provider = candidate.get("provider", "")
            # Inject provider into request so _dispatch() can apply privacy gate per-provider
            routed_request = {**request, "provider": provider} if provider else request
            start = time.time()
            try:
                result = ModelArchitectureRouter.route(arch, routed_request)
                latency_ms = (time.time() - start) * 1000
                result["candidate_count"] = candidate_count
                result["selected_rank"] = rank
                result["fallback_used"] = rank > 0
                ok = result.get("status") not in ("error", "blocked")
                # Record to performance tracker regardless of outcome
                tracker.record(arch, provider, provider, latency_ms, "ok" if ok else "error")
                if ok:
                    return result
                # Blacklist this provider for 60s after consecutive failure
                if result.get("status") == "error":
                    monitor.blacklist(f"model:{arch}:{provider}", duration_s=60.0)
                last_error = result.get("error", "error")
            except Exception as exc:
                latency_ms = (time.time() - start) * 1000
                tracker.record(arch, provider, provider, latency_ms, "error")
                monitor.blacklist(f"model:{arch}:{provider}", duration_s=60.0)
                last_error = str(exc)

        return {"status": "error", "arch": arch, "error": last_error, "candidate_count": candidate_count}

    @staticmethod
    def get_registry() -> dict:
        import json
        from pathlib import Path
        registry_path = Path(__file__).parent / "model_registry.json"
        try:
            with open(registry_path) as f:
                return json.load(f)
        except Exception:
            return {arch: [] for arch in ModelArchitectureRouter.ARCHS}
