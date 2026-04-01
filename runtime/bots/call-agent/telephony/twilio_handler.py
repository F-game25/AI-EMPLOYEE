"""Twilio Telephony Handler — TwiML generation and signature validation.

Provides helpers for:
  - Generating TwiML responses (Gather, Say, Play, Hangup, Redirect)
  - Validating Twilio request signatures for webhook security
  - Parsing incoming Twilio webhook parameters

All TwiML is returned as plain XML strings for use with FastAPI PlainTextResponse.
"""
import hashlib
import hmac
import logging
import os
import urllib.parse
from base64 import b64encode
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger("call-agent.telephony")

TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
CALL_AGENT_BASE_URL = os.environ.get("CALL_AGENT_BASE_URL", "").rstrip("/")

GATHER_TIMEOUT = int(os.environ.get("CALL_GATHER_TIMEOUT", "5"))
GATHER_SPEECH_TIMEOUT = os.environ.get("CALL_SPEECH_TIMEOUT", "auto")
GATHER_LANGUAGE = os.environ.get("CALL_LANGUAGE", "nl-NL")
VOICE_NAME = os.environ.get("CALL_VOICE_NAME", "Polly.Lotte")

_TWIML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'


def _say(text: str, voice: str = VOICE_NAME) -> str:
    return f'<Say voice="{voice}" language="{GATHER_LANGUAGE}">{xml_escape(text)}</Say>'


def _play(url: str) -> str:
    return f"<Play>{xml_escape(url)}</Play>"


def _gather_wrap(inner: str, action: str, method: str = "POST") -> str:
    speech_timeout = GATHER_SPEECH_TIMEOUT
    return (
        f'<Gather input="speech" action="{xml_escape(action)}" method="{method}" '
        f'language="{GATHER_LANGUAGE}" speechTimeout="{speech_timeout}" '
        f'timeout="{GATHER_TIMEOUT}">'
        f"{inner}"
        f"</Gather>"
    )


def build_greeting_twiml(greeting_text: str) -> str:
    """TwiML for the opening greeting — says text and waits for speech."""
    if not CALL_AGENT_BASE_URL:
        logger.warning("CALL_AGENT_BASE_URL is not set — Gather action URL will be relative")
    action_url = f"{CALL_AGENT_BASE_URL}/webhook/call/speech" if CALL_AGENT_BASE_URL else "/webhook/call/speech"
    inner = _say(greeting_text)
    gather = _gather_wrap(inner, action_url)
    fallback = _say("Ik hoorde niets — belt u ons even terug?")
    return f"{_TWIML_HEADER}<Response>{gather}{fallback}</Response>"


def build_response_twiml(response_text: str, audio_url: str = "") -> str:
    """TwiML to speak a response then gather the next user turn."""
    action_url = f"{CALL_AGENT_BASE_URL}/webhook/call/speech" if CALL_AGENT_BASE_URL else "/webhook/call/speech"
    if audio_url:
        inner = _play(audio_url)
    else:
        inner = _say(response_text)
    gather = _gather_wrap(inner, action_url)
    fallback = _say("Tot ziens!")
    return f"{_TWIML_HEADER}<Response>{gather}{fallback}</Response>"


def build_hangup_twiml(farewell_text: str = "", audio_url: str = "") -> str:
    """TwiML to say goodbye and hang up."""
    if audio_url:
        speech = _play(audio_url)
    elif farewell_text:
        speech = _say(farewell_text)
    else:
        speech = ""
    return f"{_TWIML_HEADER}<Response>{speech}<Hangup/></Response>"


def build_transfer_twiml(transfer_number: str, message: str = "") -> str:
    """TwiML to announce transfer and dial an agent."""
    say = _say(message) if message else ""
    dial = f"<Dial>{xml_escape(transfer_number)}</Dial>"
    return f"{_TWIML_HEADER}<Response>{say}{dial}</Response>"


def build_fallback_twiml() -> str:
    """TwiML for the error/fallback path — connect to human agent."""
    transfer_number = os.environ.get("CALL_TRANSFER_NUMBER", "")
    fallback_msg = os.environ.get(
        "CALL_FALLBACK_RESPONSE",
        "Sorry, een moment — ik verbind je door met een collega.",
    )
    if transfer_number:
        return build_transfer_twiml(transfer_number, fallback_msg)
    return build_hangup_twiml(farewell_text=fallback_msg)


def validate_twilio_signature(auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Validate an X-Twilio-Signature header using HMAC-SHA1.

    See: https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    computed = b64encode(
        hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(computed, signature)


def parse_twilio_params(raw_body: bytes) -> dict:
    """Parse URL-encoded Twilio webhook body into a plain dict."""
    try:
        return dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
    except Exception:
        return {}
