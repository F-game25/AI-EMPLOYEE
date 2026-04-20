"""ASCEND AI — Chat Router"""

import logging
import os

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

SYSTEM_PROMPTS: dict[str, str] = {
    "main": (
        "You are ASCEND AI, an autonomous multi-agent business assistant "
        "with 20 specialist agents. Keep responses concise and actionable."
    ),
    "forge": (
        "You are the ASCEND Forge AI, a self-improvement agent. You analyse the ASCEND AI "
        "codebase, propose optimisations, run sandbox tests, and report results. "
        "Be specific about code paths, performance gains, and test outcomes. "
        "Always mention risk level (LOW/MEDIUM/HIGH) for proposed changes."
    ),
    "money": (
        "You are the Money Mode AI, a business automation specialist focused on lead "
        "generation, revenue optimisation, and print-on-demand automation. "
        "Give concrete, actionable advice on leads, revenue streams, automation flows, "
        "and business growth. Quantify impact where possible (e.g. estimated €/week)."
    ),
    "blacklight": (
        "You are the Blacklight Security AI, a security monitoring specialist. "
        "You monitor connections, detect threats, and ensure safe operation. "
        "Report security events clearly with severity levels. "
        "Always advise whether action is required immediately or can wait."
    ),
    "hermes": (
        "You are Hermes, the coordination and communication agent for ASCEND AI. "
        "You route tasks to the correct specialist agents, summarise system activity, "
        "handle WhatsApp/Telegram notification routing, and act as the human-facing "
        "coordinator. When routing tasks, specify which agent handles it and why."
    ),
    "doctor": (
        "You are the Doctor AI, a diagnostics specialist for the ASCEND AI system. "
        "Analyse system health metrics, interpret log patterns, track performance, "
        "and recommend fixes. Be precise about error causes and remediation steps."
    ),
}


class ChatRequest(BaseModel):
    message: str
    context: str = "main"


@router.post("/chat")
async def chat(req: ChatRequest):
    system_prompt = SYSTEM_PROMPTS.get(req.context, SYSTEM_PROMPTS["main"])
    api_key = _get_key()
    if not api_key:
        from services.mock_layer import get_mock_chat_response

        mock_msg = get_mock_chat_response()
        return {"role": "ai", "content": mock_msg, "mock": True}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": req.message}],
                },
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("content", [{}])[0].get("text", "")
        if not text:
            text = "No response received from AI. Check your API key and try again."
        return {"role": "ai", "content": text}
    except httpx.HTTPStatusError as exc:
        error_msg = f"AI API error {exc.response.status_code}: {exc.response.text[:200]}"
        logger.error(error_msg)
        return {"role": "ai", "content": error_msg, "error": True}
    except httpx.TimeoutException:
        error_msg = "AI request timed out after 30s. The model may be busy — please try again."
        logger.error(error_msg)
        return {"role": "ai", "content": error_msg, "error": True}
    except Exception as exc:
        error_msg = f"Unexpected error calling AI: {exc}"
        logger.error(error_msg)
        return {"role": "ai", "content": error_msg, "error": True}


def _get_key() -> str | None:
    """Read API key from ~/.ai-employee/.env or environment."""
    env_path = os.path.expanduser("~/.ai-employee/.env")
    if not os.path.exists(env_path):
        return os.environ.get("ANTHROPIC_API_KEY")
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError as exc:
        logger.warning("Could not read ~/.ai-employee/.env: %s", exc)
    return os.environ.get("ANTHROPIC_API_KEY")
