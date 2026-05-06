"""Latent Consistency Model routing — image generation (STUB)."""
import logging

logger = logging.getLogger(__name__)


def route_lcm(request: dict) -> dict:
    """Route to LCM (image generation). Requires ComfyUI/A1111 + GPU.

    This is a stub. To enable:
    1. Set NEURAL_BRAIN_LCM_ENABLED=true
    2. Set LCM_BACKEND_URL=http://localhost:7860 (A1111) or ComfyUI endpoint
    """
    try:
        import os
        import httpx

        backend_url = os.getenv("LCM_BACKEND_URL")
        if not backend_url:
            return {
                "status": "disabled",
                "reason": "LCM_BACKEND_URL not configured",
            }

        prompt = request.get("prompt", "")
        negative_prompt = request.get("negative_prompt", "")

        if not prompt:
            return {"status": "error", "error": "Missing prompt"}

        # POST to Stable Diffusion WebUI or ComfyUI
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": min(request.get("steps", 20), 50),
            "guidance_scale": request.get("guidance_scale", 7.5),
            "height": request.get("height", 512),
            "width": request.get("width", 512),
        }

        resp = httpx.post(f"{backend_url}/api/generate", json=payload, timeout=60.0)
        resp.raise_for_status()
        result = resp.json()

        return {
            "status": "success",
            "output": result.get("image"),
            "provider": "lcm",
            "model": "stable-diffusion-lcm",
        }

    except Exception as e:
        logger.error(f"route_lcm failed: {e}")
        return {"status": "error", "error": str(e)}
