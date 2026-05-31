"""Neural Brain runtime settings, sourced from environment."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: str) -> Path:
    p = Path(os.getenv(name, default)).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


class NeuralBrainSettings:
    def __init__(self) -> None:
        self.enabled = _bool("NEURAL_BRAIN_ENABLED", True)
        self.hook_pipeline = _bool("NEURAL_BRAIN_HOOK_PIPELINE", False)
        self.proxy_legacy = _bool("NEURAL_BRAIN_PROXY_LEGACY", False)
        self.lcm_enabled = _bool("NEURAL_BRAIN_LCM_ENABLED", False)
        self.sam_enabled = _bool("NEURAL_BRAIN_SAM_ENABLED", False)
        self.lcm_backend_url = os.getenv("NEURAL_BRAIN_LCM_BACKEND_URL", "")

        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "neuralbrain")

        self.chroma_dir = _path("NEURAL_BRAIN_CHROMA_DIR", "state/neural_brain/chroma")
        self.mem0_dir = _path("NEURAL_BRAIN_MEM0_DIR", "state/neural_brain/mem0")
        self.traces_dir = _path("NEURAL_BRAIN_TRACES_DIR", "state/neural_brain/traces")

        self.embed_model = os.getenv("NEURAL_BRAIN_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.ollama_host = os.getenv("NEURAL_BRAIN_OLLAMA_HOST", os.getenv("OLLAMA_HOST", "http://localhost:11434"))
        self.llm_model = os.getenv("NEURAL_BRAIN_LLM_MODEL", "llama3.1:8b")
        self.slm_model = os.getenv("NEURAL_BRAIN_SLM_MODEL", "phi3:mini")
        self.moe_model = os.getenv("NEURAL_BRAIN_MOE_MODEL", "mixtral:8x7b-instruct-q4_K_M")
        self.vlm_model = os.getenv("NEURAL_BRAIN_VLM_MODEL", "llava:7b")

        self.node_bridge_url = os.getenv("NEURAL_BRAIN_NODE_BRIDGE_URL", "http://localhost:8787/internal/events")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

        # ── Privacy + telemetry ───────────────────────────────────────────────
        self.privacy_mode = os.getenv("PRIVACY_MODE", "HYBRID")   # OFFLINE | HYBRID | CONNECTED
        self.telemetry_enabled = os.getenv("TELEMETRY_ENABLED", "0") in ("1", "true", "yes")
        self.telemetry_endpoint = os.getenv("TELEMETRY_ENDPOINT", "")
        self.auto_update = os.getenv("AUTO_UPDATE", "0") in ("1", "true", "yes")
        self.update_endpoint = os.getenv("UPDATE_ENDPOINT", "")

        # ── Auth bootstrap ────────────────────────────────────────────────────
        self.admin_username = os.getenv("ADMIN_USERNAME", "admin")
        self.admin_password = os.getenv("ADMIN_PASSWORD", "")
        self.admin_email    = os.getenv("ADMIN_EMAIL", "admin@nexus.local")


@lru_cache(maxsize=1)
def get_settings() -> NeuralBrainSettings:
    return NeuralBrainSettings()
