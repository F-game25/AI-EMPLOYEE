"""Mixture of Experts routing — Mixtral or Qwen2.5-MoE."""
import logging

logger = logging.getLogger(__name__)


def route_moe(request: dict) -> dict:
    """Route to MoE model (Mixtral via Ollama or OpenRouter fallback)."""
    try:
        import ollama

        prompt = request.get("prompt", "")
        if not prompt:
            return {"status": "error", "error": "Missing prompt"}

        # Try local Ollama MoE (resolver-injected model preferred — hardware-aware)
        model = request.get("model") or "mixtral:8x7b-instruct-q4_K_M"
        try:
            response = ollama.generate(
                model=model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": request.get("temperature", 0.7),
                    "num_predict": request.get("max_tokens", 1024),
                },
            )
            return {
                "status": "success",
                "output": response.get("response", ""),
                "provider": "ollama",
                "model": model,
            }
        except Exception as e:
            # Fallback to Qwen2.5-MoE if Mixtral not available
            logger.debug(f"Mixtral unavailable ({e}), trying Qwen2.5-MoE")
            try:
                model = "qwen2.5-moe"
                response = ollama.generate(
                    model=model,
                    prompt=prompt,
                    stream=False,
                    options={
                        "temperature": request.get("temperature", 0.7),
                        "num_predict": request.get("max_tokens", 1024),
                    },
                )
                return {
                    "status": "success",
                    "output": response.get("response", ""),
                    "provider": "ollama",
                    "model": model,
                }
            except Exception as e2:
                # Last resort: OpenRouter if configured
                logger.debug(f"Local MoE unavailable ({e2}), trying OpenRouter")
                try:
                    import os
                    import httpx

                    api_key = os.getenv("OPENROUTER_API_KEY")
                    if not api_key:
                        raise ValueError("OPENROUTER_API_KEY not set")

                    resp = httpx.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": "mistralai/mixtral-8x7b-instruct",
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": request.get("temperature", 0.7),
                            "max_tokens": request.get("max_tokens", 1024),
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    return {
                        "status": "success",
                        "output": result["choices"][0]["message"]["content"],
                        "provider": "openrouter",
                        "model": "mistralai/mixtral-8x7b-instruct",
                    }
                except Exception as e3:
                    return {"status": "error", "error": f"All MoE backends failed: {e3}"}

    except Exception as e:
        logger.error(f"route_moe failed: {e}")
        return {"status": "error", "error": str(e)}
