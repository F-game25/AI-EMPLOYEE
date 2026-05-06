"""Small Language Model routing — fast, on-device models."""
import logging

logger = logging.getLogger(__name__)


def route_slm(request: dict) -> dict:
    """Route to lightweight SLM (phi3:mini, qwen2.5:1.5b)."""
    try:
        import ollama

        prompt = request.get("prompt", "")
        if not prompt:
            return {"status": "error", "error": "Missing prompt"}

        # Try phi3:mini first, fallback to qwen2.5:1.5b
        model = "phi3:mini"
        try:
            response = ollama.generate(
                model=model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": request.get("temperature", 0.7),
                    "num_predict": min(request.get("max_tokens", 256), 512),
                },
            )
            output = response.get("response", "")
        except Exception:
            model = "qwen2.5:1.5b"
            response = ollama.generate(
                model=model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": request.get("temperature", 0.7),
                    "num_predict": min(request.get("max_tokens", 256), 512),
                },
            )
            output = response.get("response", "")

        return {
            "status": "success",
            "output": output,
            "provider": "ollama",
            "model": model,
        }

    except Exception as e:
        logger.warning(f"route_slm failed: {e}")
        return {"status": "error", "error": str(e)}
