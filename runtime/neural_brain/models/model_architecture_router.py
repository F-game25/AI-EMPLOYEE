"""Route requests to the appropriate model architecture."""
import logging
from typing import Literal

from runtime.neural_brain.core.feature_flags import FeatureFlags
from runtime.neural_brain.api.node_bridge import emit

logger = logging.getLogger(__name__)

Arch = Literal["LLM", "SLM", "MoE", "VLM", "MLM", "LAM", "LCM", "SAM"]


class ModelArchitectureRouter:
    """Dispatch inference requests to 8 model architectures."""

    ARCHS = ("LLM", "SLM", "MoE", "VLM", "MLM", "LAM", "LCM", "SAM")

    @staticmethod
    def route(arch: Arch, request: dict) -> dict:
        """Route a request to the specified architecture.

        Args:
            arch: One of 8 architecture names
            request: {prompt, images?, max_tokens?, temperature?, ...}

        Returns:
            {status, output?, error?, latency_ms}
        """
        import time

        start = time.time()
        flags = FeatureFlags()

        try:
            if arch == "LLM":
                from runtime.neural_brain.models.llm_backend import route_llm

                result = route_llm(request)
            elif arch == "SLM":
                from runtime.neural_brain.models.slm_backend import route_slm

                result = route_slm(request)
            elif arch == "MoE":
                from runtime.neural_brain.models.moe_backend import route_moe

                result = route_moe(request)
            elif arch == "VLM":
                from runtime.neural_brain.models.vlm_backend import route_vlm

                result = route_vlm(request)
            elif arch == "MLM":
                from runtime.neural_brain.models.mlm_backend import route_mlm

                result = route_mlm(request)
            elif arch == "LAM":
                from runtime.neural_brain.models.lam_backend import route_lam

                result = route_lam(request)
            elif arch == "LCM":
                if not flags.is_lcm_enabled():
                    result = {
                        "status": "disabled",
                        "arch": arch,
                        "reason": "Image generation disabled (requires GPU + NEURAL_BRAIN_LCM_ENABLED=true)",
                    }
                else:
                    from runtime.neural_brain.models.lcm_backend import route_lcm

                    result = route_lcm(request)
            elif arch == "SAM":
                if not flags.is_sam_enabled():
                    result = {
                        "status": "disabled",
                        "arch": arch,
                        "reason": "Segmentation disabled (requires ~2.4GB + NEURAL_BRAIN_SAM_ENABLED=true)",
                    }
                else:
                    from runtime.neural_brain.models.sam_backend import route_sam

                    result = route_sam(request)
            else:
                result = {"status": "error", "error": f"Unknown architecture: {arch}"}

            latency_ms = (time.time() - start) * 1000
            result["latency_ms"] = latency_ms
            result["arch"] = arch

            # Emit telemetry
            emit("nb:model_call", {
                "arch": arch,
                "status": result.get("status"),
                "latency_ms": latency_ms,
                "provider": result.get("provider"),
            })

            return result

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            logger.error(f"route({arch}) failed: {e}")
            result = {
                "status": "error",
                "arch": arch,
                "error": str(e),
                "latency_ms": latency_ms,
            }
            emit("nb:model_call", {"arch": arch, "status": "error", "latency_ms": latency_ms})
            return result

    @staticmethod
    def get_registry() -> dict:
        """Fetch model registry with primary/fallback options per arch."""
        import json
        from pathlib import Path

        registry_path = Path(__file__).parent / "model_registry.json"
        try:
            with open(registry_path) as f:
                return json.load(f)
        except Exception:
            return {arch: [] for arch in ModelArchitectureRouter.ARCHS}
