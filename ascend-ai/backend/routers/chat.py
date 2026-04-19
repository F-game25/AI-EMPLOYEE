"""ASCEND AI — Chat Router"""

import os

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    context: str = "main"


@router.post("/chat")
async def chat(req: ChatRequest):
    api_key = _get_key()
    if not api_key:
        from services.mock_layer import get_mock_chat_response

        return {"role": "ai", "content": get_mock_chat_response()}

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
                "system": (
                    "You are ASCEND AI, an autonomous multi-agent business assistant "
                    "with 20 specialist agents. Keep responses concise and actionable."
                ),
                "messages": [{"role": "user", "content": req.message}],
            },
            timeout=30,
        )
    data = resp.json()
    text = data.get("content", [{}])[0].get("text", "No response.")
    return {"role": "ai", "content": text}


def _get_key() -> str | None:
    """Read API key from ~/.ai-employee/.env or environment."""
    env_path = os.path.expanduser("~/.ai-employee/.env")
    if not os.path.exists(env_path):
        return os.environ.get("ANTHROPIC_API_KEY")
    with open(env_path) as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return None
