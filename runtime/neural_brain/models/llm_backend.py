"""Large Language Model routing."""
import logging

logger = logging.getLogger(__name__)


def route_llm(request: dict) -> dict:
    """Route to LLM via orchestrator.LLMClient + model_routing."""
    try:
        from core.orchestrator import get_llm_client
        from core.model_routing import select_model_route

        prompt = request.get("prompt", "")
        if not prompt:
            return {"status": "error", "error": "Missing prompt"}

        # Fast path: a resolver-injected Ollama model (hardware-aware) — run it directly
        # so the chosen model actually takes effect instead of the env default.
        inj_model = request.get("model")
        if inj_model and request.get("provider", "ollama") == "ollama":
            try:
                import ollama
                resp = ollama.generate(
                    model=inj_model, prompt=prompt, stream=False,
                    options={
                        "temperature": request.get("temperature", 0.7),
                        "num_predict": request.get("max_tokens", 1024),
                    },
                )
                return {"status": "success", "output": resp.get("response", ""),
                        "provider": "ollama", "model": inj_model}
            except Exception as e:  # noqa: BLE001 — fall through to orchestrator routing
                logger.debug("llm injected-model path failed (%s); falling back to orchestrator", e)

        # Select the best route (Anthropic/Ollama/Groq/OpenRouter)
        route = select_model_route("general")
        client = get_llm_client()

        result = client.invoke(
            prompt,
            max_tokens=request.get("max_tokens", 1024),
            temperature=request.get("temperature", 0.7),
        )

        output = result.get("output", result) if isinstance(result, dict) else result

        return {
            "status": "success",
            "output": output,
            "provider": route.get("provider") if isinstance(route, dict) else "unknown",
            "model": route.get("model") if isinstance(route, dict) else "unknown",
        }

    except Exception as e:
        logger.error(f"route_llm failed: {e}")
        return {"status": "error", "error": str(e)}
