from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestTier:
    tier: str
    estimated_tokens: int
    threshold: int


@dataclass(frozen=True)
class RouteSelection:
    model_route: str
    force_model: str | None
    tier: str
    estimated_tokens: int
    threshold: int
    rollout_mode: str
    shadow_wavefield: bool


def estimate_tokens(*parts: str | None) -> int:
    text = " ".join(p for p in parts if p).strip()
    return max(1, len(text) // 4) if text else 0


def classify_request_tier(prompt: str, context: str | None = None) -> RequestTier:
    estimated_tokens = estimate_tokens(context, prompt)
    threshold = int(os.environ.get("WAVEFIELD_ROUTE_MIN_TOKENS", "8000"))
    tier = "long" if estimated_tokens >= threshold else "short"
    return RequestTier(tier=tier, estimated_tokens=estimated_tokens, threshold=threshold)


def wavefield_enabled() -> bool:
    return os.environ.get("WAVEFIELD_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _rollout_mode() -> str:
    mode = os.environ.get("WAVEFIELD_ROLLOUT_MODE", "default").strip().lower()
    return mode if mode in {"off", "canary", "default", "shadow"} else "default"


def _canary_bucket(prompt: str, percent: int) -> bool:
    digest = hashlib.md5(prompt.encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324
    bucket = int(digest[:8], 16) % 100
    return bucket < max(0, min(100, percent))


def select_model_route(
    *,
    prompt: str,
    context: str | None = None,
    requested_route: str | None = None,
    default_route: str = "auto",
) -> RouteSelection:
    tier = classify_request_tier(prompt=prompt, context=context)
    route = (requested_route or "").strip().lower() or default_route
    rollout_mode = _rollout_mode()
    if requested_route:
        return RouteSelection(
            model_route=route,
            force_model=None,
            tier=tier.tier,
            estimated_tokens=tier.estimated_tokens,
            threshold=tier.threshold,
            rollout_mode=rollout_mode,
            shadow_wavefield=False,
        )

    if tier.tier == "long" and wavefield_enabled() and rollout_mode != "off":
        if rollout_mode == "shadow":
            return RouteSelection(
                model_route=route,
                force_model=None,
                tier=tier.tier,
                estimated_tokens=tier.estimated_tokens,
                threshold=tier.threshold,
                rollout_mode=rollout_mode,
                shadow_wavefield=True,
            )
        if rollout_mode == "canary":
            canary_percent = int(os.environ.get("WAVEFIELD_CANARY_PERCENT", "10"))
            if not _canary_bucket(prompt=prompt, percent=canary_percent):
                return RouteSelection(
                    model_route=route,
                    force_model=None,
                    tier=tier.tier,
                    estimated_tokens=tier.estimated_tokens,
                    threshold=tier.threshold,
                    rollout_mode=rollout_mode,
                    shadow_wavefield=False,
                )
        return RouteSelection(
            model_route="wavefield",
            force_model=os.environ.get("WAVEFIELD_MODEL", "").strip() or None,
            tier=tier.tier,
            estimated_tokens=tier.estimated_tokens,
            threshold=tier.threshold,
            rollout_mode=rollout_mode,
            shadow_wavefield=False,
        )

    return RouteSelection(
        model_route=route,
        force_model=None,
        tier=tier.tier,
        estimated_tokens=tier.estimated_tokens,
        threshold=tier.threshold,
        rollout_mode=rollout_mode,
        shadow_wavefield=False,
    )
