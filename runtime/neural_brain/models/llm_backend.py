"""Large Language Model routing."""
import logging

logger = logging.getLogger(__name__)


def route_llm(request: dict) -> dict:
    """Route to LLM via orchestrator.LLMClient + model_routing."""
    try:
        from runtime.core.orchestrator import get_llm_client
        from runtime.core.model_routing import select_model_route

        prompt = request.get("prompt", "")
        if not prompt:
            return {"status": "error", "error": "Missing prompt"}

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
