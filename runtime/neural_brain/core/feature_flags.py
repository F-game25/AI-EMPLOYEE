"""Feature flags for Neural Brain subsystems."""
import os


class FeatureFlags:
    """Centralized feature control."""

    @staticmethod
    def is_lcm_enabled() -> bool:
        """Image generation (Stable Diffusion) requires GPU."""
        return os.getenv("NEURAL_BRAIN_LCM_ENABLED", "false").lower() == "true"

    @staticmethod
    def is_sam_enabled() -> bool:
        """Segment Anything requires ~2.4 GB weights."""
        return os.getenv("NEURAL_BRAIN_SAM_ENABLED", "false").lower() == "true"

    @staticmethod
    def is_hook_pipeline_enabled() -> bool:
        """Hook into existing pipeline for hybrid reasoning."""
        return os.getenv("NEURAL_BRAIN_HOOK_PIPELINE", "false").lower() == "true"

    @staticmethod
    def is_reranking_enabled() -> bool:
        """Cross-encoder reranking on recalls."""
        return os.getenv("NEURAL_BRAIN_RERANKING", "false").lower() == "true"
