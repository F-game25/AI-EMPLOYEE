"""FastAPI webhook routes for the AI call agent.

Endpoints:
  POST /webhook/call/start   — Twilio calls this when a new call connects
  POST /webhook/call/speech  — Twilio calls this with each SpeechResult
  POST /webhook/call/status  — Twilio calls this for call status updates
  GET  /health               — health / liveness probe
  GET  /leads                — summary of captured leads (internal)
  GET  /calls                — summary of completed calls (internal)
  GET  /tts/<filename>       — serve cached TTS audio files

Request validation:
  When TWILIO_AUTH_TOKEN is set, every POST is validated with HMAC-SHA1.
  Requests with an invalid or missing signature return HTTP 403.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

_bot_dir = Path(__file__).parent.parent
for _sub in ("llm", "memory", "stt", "telephony", "tts"):
    _p = str(_bot_dir / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from llm_engine import generate_response, get_greeting  # type: ignore
from conversation_manager import get_manager  # type: ignore
from whisper_stt import transcribe_text, transcribe_url  # type: ignore
from twilio_handler import (  # type: ignore
    TWILIO_AUTH_TOKEN,
    build_fallback_twiml,
    build_greeting_twiml,
    build_hangup_twiml,
    build_response_twiml,
    parse_twilio_params,
    validate_twilio_signature,
)
from voxtral_tts import TTS_CACHE_DIR, synthesize  # type: ignore

logger = logging.getLogger("call-agent.routes")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
LEADS_FILE = AI_HOME / "state" / "call-agent-leads.json"
CALLS_FILE = AI_HOME / "state" / "call-agent-calls.json"

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _xml(content: str) -> PlainTextResponse:
    return PlainTextResponse(content, media_type="application/xml")


async def _get_params(request: Request) -> dict:
    body = await request.body()
    return parse_twilio_params(body)


def _check_signature(request: Request, params: dict, signature: str) -> None:
    if not TWILIO_AUTH_TOKEN:
        return
    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-Twilio-Signature")
    if not validate_twilio_signature(TWILIO_AUTH_TOKEN, str(request.url), params, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")


@router.post("/webhook/call/start", response_class=PlainTextResponse)
async def call_start(
    request: Request,
    x_twilio_signature: str = Header(default="", alias="X-Twilio-Signature"),
) -> PlainTextResponse:
    """Handle new inbound call — greet the caller and start gathering speech."""
    params = await _get_params(request)
    _check_signature(request, params, x_twilio_signature)

    call_sid = params.get("CallSid", "unknown")
    caller = params.get("From", "")

    manager = get_manager()
    session = manager.get_or_create(call_sid, caller)
    greeting = get_greeting()
    manager.add_message(call_sid, "assistant", greeting)

    logger.info("Call started: sid=%s from=%s", call_sid, caller or "unknown")
    return _xml(build_greeting_twiml(greeting))


@router.post("/webhook/call/speech", response_class=PlainTextResponse)
async def call_speech(
    request: Request,
    x_twilio_signature: str = Header(default="", alias="X-Twilio-Signature"),
) -> PlainTextResponse:
    """Handle a speech turn — transcribe, generate response, return TwiML."""
    params = await _get_params(request)
    _check_signature(request, params, x_twilio_signature)

    call_sid = params.get("CallSid", "unknown")
    caller = params.get("From", "")
    speech_result = params.get("SpeechResult", "").strip()
    recording_url = params.get("RecordingUrl", "")

    manager = get_manager()
    session = manager.get_or_create(call_sid, caller)

    if speech_result:
        user_text = transcribe_text(speech_result)
    elif recording_url:
        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        auth = (twilio_sid, twilio_token) if twilio_sid and twilio_token else None
        user_text = transcribe_url(recording_url, auth=auth)
    else:
        user_text = ""

    if not user_text:
        response_text = "Ik hoorde u niet goed — kunt u dat herhalen?"
        manager.add_message(call_sid, "assistant", response_text)
        audio_url = synthesize(response_text) or ""
        return _xml(build_response_twiml(response_text, audio_url))

    manager.add_message(call_sid, "user", user_text)

    history = manager.get_history(call_sid)
    intent = session.get("intent", "unknown")
    turn = session.get("turn", 0)

    response_text, updated_intent = generate_response(user_text, history, intent, turn)
    manager.add_message(call_sid, "assistant", response_text)
    manager.update(call_sid, intent=updated_intent)

    if updated_intent == "appointment":
        manager.update(call_sid, appointment_booked=True)

    logger.info(
        "Speech turn: sid=%s intent=%s user=%r response=%r",
        call_sid, updated_intent, user_text[:60], response_text[:60],
    )

    audio_url = synthesize(response_text) or ""
    return _xml(build_response_twiml(response_text, audio_url))


@router.post("/webhook/call/status", response_class=PlainTextResponse)
async def call_status(
    request: Request,
    x_twilio_signature: str = Header(default="", alias="X-Twilio-Signature"),
) -> PlainTextResponse:
    """Handle Twilio status callbacks — persist session on call completion."""
    params = await _get_params(request)
    _check_signature(request, params, x_twilio_signature)

    call_sid = params.get("CallSid", "unknown")
    status = params.get("CallStatus", "")
    caller = params.get("From", "")

    logger.info("Call status: sid=%s status=%s from=%s", call_sid, status, caller)

    if status in ("completed", "busy", "failed", "no-answer", "canceled"):
        get_manager().close_call(call_sid)

    return PlainTextResponse("", media_type="application/xml")


@router.get("/health")
async def health() -> dict:
    leads_count = 0
    calls_count = 0
    try:
        if LEADS_FILE.exists():
            leads_count = len(json.loads(LEADS_FILE.read_text()).get("leads", []))
        if CALLS_FILE.exists():
            calls_count = len(json.loads(CALLS_FILE.read_text()).get("calls", []))
    except Exception:
        pass
    return {
        "status": "ok",
        "ts": _now_iso(),
        "leads": leads_count,
        "calls": calls_count,
    }


@router.get("/leads")
async def leads_summary() -> dict:
    if not LEADS_FILE.exists():
        return {"leads": []}
    try:
        return json.loads(LEADS_FILE.read_text())
    except Exception:
        return {"leads": [], "error": "could not read leads file"}


@router.get("/calls")
async def calls_summary() -> dict:
    if not CALLS_FILE.exists():
        return {"calls": []}
    try:
        return json.loads(CALLS_FILE.read_text())
    except Exception:
        return {"calls": [], "error": "could not read calls file"}


@router.get("/tts/{filename}")
async def serve_tts(filename: str) -> FileResponse:
    path = TTS_CACHE_DIR / filename
    if not path.exists() or not path.name.endswith(".mp3"):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(path), media_type="audio/mpeg")
