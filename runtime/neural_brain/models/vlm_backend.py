"""Vision Language Model routing — llava:7b."""
import logging
import base64

logger = logging.getLogger(__name__)


def route_vlm(request: dict) -> dict:
    """Route to VLM (llava:7b for image understanding)."""
    try:
        import ollama

        prompt = request.get("prompt", "")
        images = request.get("images", [])  # List of base64 or file paths

        if not prompt:
            return {"status": "error", "error": "Missing prompt"}
        if not images:
            return {"status": "error", "error": "Missing images"}

        # Normalize images to base64
        b64_images = []
        for img in images:
            if isinstance(img, str):
                if img.startswith("data:image"):
                    # Already base64
                    b64_images.append(img.split(",")[1] if "," in img else img)
                else:
                    # File paths are intentionally not accepted here; callers must
                    # provide base64/data URLs so VLM cannot read arbitrary files.
                    b64_images.append(img)
            else:
                return {"status": "error", "error": f"Invalid image format: {type(img)}"}

        model = request.get("model") or "llava:7b"
        response = ollama.generate(
            model=model,
            prompt=prompt,
            images=b64_images,
            stream=False,
            options={
                "temperature": request.get("temperature", 0.7),
                "num_predict": request.get("max_tokens", 512),
            },
        )

        return {
            "status": "success",
            "output": response.get("response", ""),
            "provider": "ollama",
            "model": model,
        }

    except Exception as e:
        logger.error(f"route_vlm failed: {e}")
        return {"status": "error", "error": str(e)}
