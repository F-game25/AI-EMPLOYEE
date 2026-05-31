"""vision_analyzer — describe images via multiple vision providers.

Provider priority (auto mode):
  1. Ollama (local)       — if OLLAMA_HOST reachable and a vision model exists
  2. NVIDIA NIM (cloud)   — if NVIDIA_API_KEY is set
  3. Anthropic (cloud)    — if ANTHROPIC_API_KEY is set
  4. Graceful fallback    — returns minimal text if no provider works

Usage::

    from tools.vision_analyzer import analyze_image

    result = analyze_image("/path/to/image.png")
    result = analyze_image("/path/to/image.png", provider="ollama")
    # Returns: { text, file_type, source_file, metadata, provider_used }
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MEDIA_TYPES = {
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "gif":  "image/gif",
    "webp": "image/webp",
}

_VISION_PROMPT = (
    "Describe this image in detail for knowledge indexing. "
    "Include all text visible, objects, charts, diagrams, and any "
    "information that would be useful for search."
)

_OLLAMA_VISION_MODELS = ["llava", "bakllava", "llama3.2-vision", "llava-phi3", "moondream"]
_NVIDIA_VISION_MODEL  = "meta/llama-3.2-11b-vision-instruct"
_NVIDIA_ENDPOINT      = "https://integrate.api.nvidia.com/v1/chat/completions"
_ANTHROPIC_MODEL      = "claude-haiku-4-5-20251001"
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9_. -]{1,160}$")


def _safe_workspace_file(file_path: str) -> Path:
    root = os.path.realpath(os.environ.get("AI_EMPLOYEE_WORKSPACE", os.getcwd()))
    filename = os.path.basename(file_path)
    if filename in {"", ".", ".."} or not _SAFE_FILE_NAME.fullmatch(filename):
        raise ValueError("invalid file name")
    candidate = os.path.normpath(os.path.join(root, filename))
    if os.path.commonpath([root, candidate]) != root:
        raise ValueError("file path is outside the allowed workspace")
    return Path(candidate)


def _workspace_file_bytes(path: Path) -> bytes:
    root = os.path.realpath(os.environ.get("AI_EMPLOYEE_WORKSPACE", os.getcwd()))
    root_fd = os.open(root, os.O_RDONLY)
    try:
        fd = os.open(path.name, os.O_RDONLY, dir_fd=root_fd)
    finally:
        os.close(root_fd)
    with os.fdopen(fd, "rb") as f:
        return f.read()


def _workspace_file_size(path: Path) -> int:
    root = os.path.realpath(os.environ.get("AI_EMPLOYEE_WORKSPACE", os.getcwd()))
    root_fd = os.open(root, os.O_RDONLY)
    try:
        return os.stat(path.name, dir_fd=root_fd).st_size
    finally:
        os.close(root_fd)


# ── Provider detection helpers ────────────────────────────────────────────────

def _ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _ollama_vision_model() -> Optional[str]:
    """Return the first available Ollama vision model name, or None."""
    try:
        data = json.loads(
            urllib.request.urlopen(f"{_ollama_host()}/api/tags", timeout=2).read()
        )
        for m in data.get("models", []):
            name = m.get("name", "").lower()
            if any(v in name for v in _OLLAMA_VISION_MODELS):
                return m["name"]
    except Exception:
        pass
    return None


def _router_provider() -> Optional[str]:
    """Ask llm_router for a configured vision subsystem provider (may be None)."""
    try:
        from core.llm_router import get_router
        provider, _ = get_router().get_route(subsystem="vision")
        return provider
    except Exception:
        return None


# ── Per-provider call implementations ────────────────────────────────────────

def _call_ollama(image_data: str, model: str) -> dict:
    payload = json.dumps({
        "model": model,
        "prompt": _VISION_PROMPT,
        "images": [image_data],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{_ollama_host()}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return {
        "text": resp.get("response", ""),
        "metadata": {"model": model, "provider": "ollama"},
        "provider_used": "ollama",
    }


def _call_nvidia(image_data: str, media_type: str) -> dict:
    data_url = f"data:{media_type};base64,{image_data}"
    payload = json.dumps({
        "model": _NVIDIA_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": _VISION_PROMPT},
            ],
        }],
        "max_tokens": 1024,
    }).encode()
    req = urllib.request.Request(
        _NVIDIA_ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('NVIDIA_API_KEY', '')}",
        },
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    text = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    return {
        "text": text,
        "metadata": {
            "model": _NVIDIA_VISION_MODEL,
            "provider": "nvidia_nim",
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        },
        "provider_used": "nvidia_nim",
    }


def _call_anthropic(image_data: str, media_type: str) -> dict:
    from anthropic import Anthropic  # noqa: PLC0415
    client = Anthropic()
    response = client.messages.create(
        model=_ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": _VISION_PROMPT},
            ],
        }],
    )
    text = response.content[0].text if response.content else ""
    return {
        "text": text,
        "metadata": {
            "model": _ANTHROPIC_MODEL,
            "provider": "anthropic",
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "provider_used": "anthropic",
    }


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_image(file_path: str, provider: Optional[str] = None) -> dict:
    """Return a text description of an image file.

    Args:
        file_path: Path to the image file.
        provider:  Force a specific provider ('ollama', 'nvidia_nim', 'anthropic').
                   None (default) → auto-detect via llm_router then env priority.

    Returns:
        { text, file_type, source_file, metadata, provider_used }
    """
    try:
        path = _safe_workspace_file(file_path)
    except ValueError as exc:
        return {"text": "", "file_type": "", "source_file": "", "provider_used": "none",
                "metadata": {"error": str(exc)}}
    ext  = path.suffix.lower().lstrip(".")
    base = {"file_type": ext, "source_file": str(file_path)}
    return {**base, "text": "", "provider_used": "none", "metadata": {"error": "managed_upload_required"}}

    media_type = _MEDIA_TYPES.get(ext, "image/jpeg")

    try:
        image_data = base64.standard_b64encode(_workspace_file_bytes(path)).decode("utf-8")
    except Exception as e:
        logger.warning("Could not read image (%s)", type(e).__name__)
        return {**base, "text": f"Image: {path.name}", "provider_used": "none",
                "metadata": {"error": type(e).__name__}}

    # Resolve provider order
    forced = provider or _router_provider()

    providers_to_try: list[str]
    if forced in ("ollama", "nvidia_nim", "anthropic"):
        providers_to_try = [forced]
    else:
        # Auto priority: local → free-cloud → paid-cloud
        providers_to_try = []
        if _ollama_vision_model():
            providers_to_try.append("ollama")
        if os.getenv("NVIDIA_API_KEY"):
            providers_to_try.append("nvidia_nim")
        if os.getenv("ANTHROPIC_API_KEY"):
            providers_to_try.append("anthropic")

    for prov in providers_to_try:
        try:
            if prov == "ollama":
                model = _ollama_vision_model()
                if not model:
                    continue
                result = _call_ollama(image_data, model)
            elif prov == "nvidia_nim":
                if not os.getenv("NVIDIA_API_KEY"):
                    continue
                result = _call_nvidia(image_data, media_type)
            elif prov == "anthropic":
                if not os.getenv("ANTHROPIC_API_KEY"):
                    continue
                result = _call_anthropic(image_data, media_type)
            else:
                continue

            result["metadata"]["file_name"] = path.name
            result["metadata"]["file_size"] = _workspace_file_size(path)
            return {**base, **result}

        except Exception as e:
            logger.warning("Vision provider %s failed (%s)", prov, type(e).__name__)

    # Graceful fallback
    logger.warning("No vision provider succeeded; returning minimal text")
    return {**base, "text": f"Image: {path.name}", "provider_used": "none", "metadata": {}}
