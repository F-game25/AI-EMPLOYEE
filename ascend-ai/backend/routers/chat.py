"""ASCEND AI — Chat Router
All chat goes through llm_router — never call providers directly here.
"""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.llm_router import get_llm_router
from websocket_manager import broadcast

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    context: str = "main"
    session_id: str = "default"


@router.post("/chat")
async def chat(req: ChatRequest):
    """
    Start a streaming chat response.
    Chunks are delivered to the frontend via WebSocket as ``chat_chunk`` messages.
    Returns immediately so the frontend can start listening on the socket.
    """
    asyncio.create_task(
        _stream_and_broadcast(req.session_id, req.context, req.message)
    )
    return {"status": "streaming"}


@router.get("/llm/status")
async def llm_status():
    """Return the active provider, model, and Ollama availability."""
    return get_llm_router().get_status()


async def _stream_and_broadcast(
    session_id: str, context: str, message: str
) -> None:
    """
    Call the LLM router and broadcast each chunk to all WebSocket clients.
    Normal chunks: ``{ type: "chat_chunk", data: { content, done, context, session_id } }``
    Error chunks:  ``{ type: "chat_error", data: { content, context, session_id } }``
    The first fallback chunk also carries ``fallback: true``.
    """
    llm = get_llm_router()
    fallback_flagged = False
    try:
        async for content, done, is_fallback, is_error in llm.stream_chat(
            session_id, context, message
        ):
            # Provider-unavailable errors → distinct message type so frontend
            # can show them without requiring an active stream.
            if is_error:
                await broadcast(
                    {
                        "type": "chat_error",
                        "data": {
                            "content": content,
                            "context": context,
                            "session_id": session_id,
                        },
                    }
                )
                return

            payload: dict = {
                "type": "chat_chunk",
                "data": {
                    "content": content,
                    "done": done,
                    "context": context,
                    "session_id": session_id,
                },
            }
            if is_fallback and not fallback_flagged:
                payload["data"]["fallback"] = True
                fallback_flagged = True
            await broadcast(payload)
    except Exception as exc:
        logger.error("Unexpected error in _stream_and_broadcast: %s", exc)
        await broadcast(
            {
                "type": "chat_error",
                "data": {
                    "content": "An error occurred. Please try again.",
                    "context": context,
                    "session_id": session_id,
                },
            }
        )
