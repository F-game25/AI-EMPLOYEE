"""AI Call Agent — Real-time voice call automation for car dealership sales.

Handles incoming Twilio calls with:
  - Greeting callers naturally
  - Understanding speech in real time (Twilio STT or Whisper)
  - Generating intelligent 2-layer responses (fast rules + Ollama LLM)
  - Speaking back via Voxtral TTS or Twilio built-in <Say>
  - Guiding conversations toward booking appointments / capturing leads

Webhook endpoints (FastAPI):
  POST /webhook/call/start   — Twilio: new call
  POST /webhook/call/speech  — Twilio: speech turn
  POST /webhook/call/status  — Twilio: call status update
  GET  /health               — liveness probe
  GET  /leads                — captured lead list (internal)
  GET  /calls                — call history (internal)
  GET  /tts/<file>           — serve synthesised audio files

Config env vars:
    CALL_AGENT_PORT      — port to listen on (default: 8791)
    CALL_AGENT_HOST      — host to bind (default: 127.0.0.1)
    CALL_AGENT_BASE_URL  — public base URL for Twilio callbacks
    TWILIO_AUTH_TOKEN    — validates webhook signatures (REQUIRED for production)
    TWILIO_ACCOUNT_SID   — Twilio account SID
    CALL_AGENT_NAME      — agent first name (default: Alex)
    CALL_DEALER_NAME     — dealership name (default: AutoPrime)
    CALL_LANGUAGE        — BCP-47 language code (default: nl-NL)
    CALL_VOICE_NAME      — Twilio Polly voice (default: Polly.Lotte)
    CALL_GATHER_TIMEOUT  — silence timeout in seconds (default: 5)
    CALL_LLM_TIMEOUT_SECONDS — max LLM response seconds (default: 4)
    CALL_TRANSFER_NUMBER — E.164 number for fallback transfer
    TTS_BACKEND          — voxtral | openai | twilio (default: auto)
    VOXTRAL_API_KEY      — Voxtral / Mistral AI TTS key
    WHISPER_MODE         — api | local (default: api when OPENAI_API_KEY set)
    LOG_LEVEL            — logging level (default: WARNING)
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(asctime)s [call-agent] %(levelname)s %(message)s",
)
logger = logging.getLogger("call-agent")

_bot_dir = Path(__file__).parent
_routes_dir = str(_bot_dir / "routes")
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from webhook_routes import router  # type: ignore  # noqa: E402

CALL_AGENT_PORT = int(os.environ.get("CALL_AGENT_PORT", "8791"))
CALL_AGENT_HOST = os.environ.get("CALL_AGENT_HOST", "127.0.0.1")

STATE_FILE = AI_HOME / "state" / "call-agent.state.json"

app = FastAPI(
    title="AI Call Agent",
    description="Real-time AI voice agent for car dealership calls",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

app.include_router(router)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_state(status: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "bot": "call-agent",
        "status": status,
        "ts": _now_iso(),
        "port": CALL_AGENT_PORT,
    }, indent=2))


def main() -> None:
    base_url = os.environ.get("CALL_AGENT_BASE_URL", "")
    if not base_url:
        logger.warning(
            "CALL_AGENT_BASE_URL is not set — Twilio cannot reach the webhooks. "
            "Set it to your public URL (e.g. https://<ngrok>.ngrok.io) in .env"
        )
    if not os.environ.get("TWILIO_AUTH_TOKEN"):
        logger.warning(
            "TWILIO_AUTH_TOKEN is not set — webhook signature validation is DISABLED. "
            "Set it in .env for production use."
        )

    _write_state("starting")
    logger.info(
        "Starting call-agent on %s:%d  base_url=%s",
        CALL_AGENT_HOST, CALL_AGENT_PORT, base_url or "(not set)",
    )
    uvicorn.run(
        app,
        host=CALL_AGENT_HOST,
        port=CALL_AGENT_PORT,
        log_level=os.environ.get("LOG_LEVEL", "warning").lower(),
    )


if __name__ == "__main__":
    main()
