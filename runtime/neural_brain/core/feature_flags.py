"""Feature flags for Neural Brain subsystems."""
import importlib.util
import os


def _lib_present(*mods: str) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in mods)


class FeatureFlags:
    """Centralized feature control."""

    @staticmethod
    def is_lcm_enabled() -> bool:
        """Local image generation (diffusers/LCM). On when diffusers is installed,
        unless explicitly overridden via NEURAL_BRAIN_LCM_ENABLED."""
        env = os.getenv("NEURAL_BRAIN_LCM_ENABLED")
        if env is not None:
            return env.lower() == "true"
        return _lib_present("diffusers", "torch")

    @staticmethod
    def is_sam_enabled() -> bool:
        """Local segmentation (segment-anything). On when the lib is installed,
        unless explicitly overridden via NEURAL_BRAIN_SAM_ENABLED."""
        env = os.getenv("NEURAL_BRAIN_SAM_ENABLED")
        if env is not None:
            return env.lower() == "true"
        return _lib_present("segment_anything", "torch", "cv2")

    @staticmethod
    def is_hook_pipeline_enabled() -> bool:
        """Hook into existing pipeline for hybrid reasoning."""
        return os.getenv("NEURAL_BRAIN_HOOK_PIPELINE", "false").lower() == "true"

    @staticmethod
    def is_reranking_enabled() -> bool:
        """Cross-encoder reranking on recalls."""
        return os.getenv("NEURAL_BRAIN_RERANKING", "false").lower() == "true"
