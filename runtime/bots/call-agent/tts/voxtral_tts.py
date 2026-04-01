"""Voxtral TTS Adapter — converts text to speech for Twilio playback.

Supports three backends (tried in order):
  1. Voxtral API  (VOXTRAL_API_KEY required)
  2. OpenAI TTS   (OPENAI_API_KEY required, model tts-1)
  3. Twilio built-in <Say>  (always available, no extra config)

When backends 1 or 2 succeed they return a publicly accessible audio URL
that can be played via Twilio <Play>.  Backend 3 returns None so the
caller falls back to Twilio's native TTS via <Say>.

Config env vars:
    TTS_BACKEND           — "voxtral" | "openai" | "twilio" (default: auto-detect)
    VOXTRAL_API_KEY       — Voxtral API key
    VOXTRAL_API_URL       — Voxtral endpoint (default: https://api.mistral.ai/v1/audio/speech)
    VOXTRAL_VOICE         — voice ID (default: "alloy")
    VOXTRAL_MODEL         — model name (default: "voxtral-mini")
    OPENAI_API_KEY        — OpenAI key (fallback TTS)
    OPENAI_TTS_VOICE      — OpenAI TTS voice (default: "alloy")
    TTS_AUDIO_CACHE_DIR   — directory to cache audio files (default: AI_HOME/state/tts_cache)
    TTS_BASE_URL          — public base URL where cached files are served (required for Voxtral/OpenAI TTS)
    TTS_TIMEOUT           — HTTP timeout for TTS API calls (default: 10)
"""
import hashlib
import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("call-agent.tts")

VOXTRAL_API_KEY = os.environ.get("VOXTRAL_API_KEY", "")
VOXTRAL_API_URL = os.environ.get("VOXTRAL_API_URL", "https://api.mistral.ai/v1/audio/speech")
VOXTRAL_VOICE = os.environ.get("VOXTRAL_VOICE", "alloy")
VOXTRAL_MODEL = os.environ.get("VOXTRAL_MODEL", "voxtral-mini")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")

TTS_TIMEOUT = int(os.environ.get("TTS_TIMEOUT", "10"))
TTS_BASE_URL = os.environ.get("TTS_BASE_URL", "").rstrip("/")

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
TTS_CACHE_DIR = Path(os.environ.get("TTS_AUDIO_CACHE_DIR", str(AI_HOME / "state" / "tts_cache")))

_BACKEND = os.environ.get(
    "TTS_BACKEND",
    "voxtral" if VOXTRAL_API_KEY else ("openai" if OPENAI_API_KEY else "twilio"),
)


def _cache_path(text: str, backend: str) -> Path:
    digest = hashlib.sha256(f"{backend}:{text}".encode()).hexdigest()[:16]
    return TTS_CACHE_DIR / f"{digest}.mp3"


def _cache_url(path: Path) -> Optional[str]:
    if not TTS_BASE_URL:
        return None
    return f"{TTS_BASE_URL}/tts/{path.name}"


def synthesize(text: str) -> Optional[str]:
    """Convert text to speech and return a public audio URL.

    Returns None if no external TTS backend is available, signalling the
    caller should use Twilio's built-in <Say> verb instead.
    """
    if _BACKEND == "twilio":
        return None

    cached = _cache_path(text, _BACKEND)
    if cached.exists() and TTS_BASE_URL:
        logger.debug("TTS cache hit: %s", cached.name)
        return _cache_url(cached)

    if _BACKEND == "voxtral":
        audio = _call_voxtral(text)
    else:
        audio = _call_openai_tts(text)

    if audio and TTS_BASE_URL:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(audio)
        return _cache_url(cached)

    return None


def _call_voxtral(text: str) -> Optional[bytes]:
    """Call the Voxtral (Mistral AI) TTS endpoint."""
    if not VOXTRAL_API_KEY:
        return None
    payload = json.dumps({
        "model": VOXTRAL_MODEL,
        "input": text,
        "voice": VOXTRAL_VOICE,
        "response_format": "mp3",
    }).encode()
    try:
        req = urllib.request.Request(
            VOXTRAL_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {VOXTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:
        logger.warning("Voxtral TTS failed: %s", exc)
        return None


def _call_openai_tts(text: str) -> Optional[bytes]:
    """Call the OpenAI TTS endpoint as fallback."""
    if not OPENAI_API_KEY:
        return None
    payload = json.dumps({
        "model": "tts-1",
        "input": text,
        "voice": OPENAI_TTS_VOICE,
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=payload,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:
        logger.warning("OpenAI TTS failed: %s", exc)
        return None
