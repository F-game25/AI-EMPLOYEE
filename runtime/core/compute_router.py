"""Compute backend availability for Forge V5.

This adapter reports what is actually available.  It does not reserve capacity
or pretend remote/API backends exist when they are not configured.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ComputeWorkload:
    # Default is the safest posture: codebase/context never leaves the machine.
    # Routing off-box requires an explicit opt-in — either a permissive
    # privacy_level or the matching *_allowed flag.
    #   privacy_level: "local_only" | "remote_allowed" | "external_api_allowed"
    task_type: str = "planning"
    privacy_level: str = "local_only"
    estimated_tokens: int = 0
    heavy: bool = False
    external_allowed: bool = False
    remote_allowed: bool = False

    @property
    def privacy(self) -> str:  # backward-compat alias for older callers
        return self.privacy_level


@dataclass
class ComputeDecision:
    backend: str
    available: bool
    reason: str
    details: dict[str, Any]


class ComputeRouter:
    def local_cpu_available(self) -> bool:
        return True

    def local_gpu_available(self) -> bool:
        if shutil.which("nvidia-smi"):
            try:
                result = subprocess.run(
                    ["nvidia-smi", "-L"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return True
            except Exception:
                pass
        if shutil.which("ollama"):
            try:
                result = subprocess.run(
                    ["ollama", "ps"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                return result.returncode == 0 and bool(result.stdout.strip())
            except Exception:
                return False
        return False

    def remote_compute_available(self) -> bool:
        return bool(os.getenv("REMOTE_COMPUTE_HOST"))

    def external_api_available(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))

    def health(self) -> dict[str, Any]:
        return {
            "local_cpu": {"available": self.local_cpu_available(), "reason": "always available"},
            "local_gpu": {"available": self.local_gpu_available(), "reason": "nvidia-smi or ollama ps detected"},
            "remote_compute": {
                "available": self.remote_compute_available(),
                "reason": "REMOTE_COMPUTE_HOST configured" if self.remote_compute_available() else "REMOTE_COMPUTE_HOST not configured",
            },
            "external_api": {
                "available": self.external_api_available(),
                "reason": "ANTHROPIC_API_KEY or OPENAI_API_KEY configured" if self.external_api_available() else "no external API key configured",
            },
        }

    def select(self, workload: ComputeWorkload) -> ComputeDecision:
        health = self.health()
        level = workload.privacy_level
        remote_permitted = workload.remote_allowed or level in ("remote_allowed", "external_api_allowed")
        external_permitted = workload.external_allowed or level == "external_api_allowed"

        # Local first — always honest, never leaves the box.
        if workload.heavy and health["local_gpu"]["available"]:
            return ComputeDecision("local_gpu", True, "heavy workload and local GPU/model process detected", health)
        # Remote compute only with explicit permission.
        if workload.heavy and remote_permitted and health["remote_compute"]["available"]:
            return ComputeDecision("remote_compute", True, "heavy workload, remote permitted and configured", health)
        # External API only with explicit permission.
        if external_permitted and health["external_api"]["available"]:
            return ComputeDecision("external_api", True, "external API permitted and configured", health)
        # Honest local fallback — if off-box was wanted but blocked by policy, say so.
        reason = "default local execution path"
        if (workload.remote_allowed or workload.external_allowed) and not (remote_permitted or external_permitted):
            reason = "off-box requested but blocked by privacy policy — using local"
        return ComputeDecision("local_cpu", True, reason, health)


def get_compute_router() -> ComputeRouter:
    return ComputeRouter()


def decision_to_dict(decision: ComputeDecision) -> dict[str, Any]:
    return asdict(decision)
