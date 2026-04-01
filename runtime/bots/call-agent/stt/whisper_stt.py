"""Whisper STT Adapter — transcribes audio URLs to text.

Supports two modes:
  1. OpenAI Whisper API  (requires OPENAI_API_KEY)
  2. Local whisper library  (pip install openai-whisper)
     Falls back to downloading the audio and passing it to the local model.

When neither is configured, returns an empty string so the LLM engine
can ask the caller to repeat themselves.

Config env vars:
    WHISPER_MODE        — "api" | "local" (default: "api" if OPENAI_API_KEY set, else "local")
    OPENAI_API_KEY      — required for "api" mode
    WHISPER_MODEL       — local model size: tiny/base/small/medium/large (default: base)
    WHISPER_TIMEOUT     — HTTP timeout for audio download in seconds (default: 10)
"""
import logging
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("call-agent.stt")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WHISPER_MODE = os.environ.get(
    "WHISPER_MODE",
    "api" if OPENAI_API_KEY else "local",
)
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
WHISPER_TIMEOUT = int(os.environ.get("WHISPER_TIMEOUT", "10"))

_local_model = None


def _get_local_model():
    global _local_model
    if _local_model is not None:
        return _local_model
    try:
        import whisper  # type: ignore
        logger.info("Loading local Whisper model '%s'…", WHISPER_MODEL_SIZE)
        _local_model = whisper.load_model(WHISPER_MODEL_SIZE)
        logger.info("Whisper model loaded.")
    except ImportError:
        logger.warning("openai-whisper not installed — STT unavailable. Run: pip install openai-whisper")
        _local_model = None
    return _local_model


def _download_audio(url: str, auth: Optional[tuple] = None) -> Optional[Path]:
    """Download audio from URL to a temp file and return the path."""
    try:
        req = urllib.request.Request(url)
        if auth:
            import base64
            credentials = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
            req.add_header("Authorization", f"Basic {credentials}")
        with urllib.request.urlopen(req, timeout=WHISPER_TIMEOUT) as resp:
            suffix = ".wav"
            content_type = resp.headers.get("Content-Type", "")
            if "ogg" in content_type:
                suffix = ".ogg"
            elif "mp3" in content_type or "mpeg" in content_type:
                suffix = ".mp3"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(resp.read())
            tmp.close()
            return Path(tmp.name)
    except Exception as exc:
        logger.warning("Audio download failed from %s: %s", url, exc)
        return None


def transcribe_url(audio_url: str, auth: Optional[tuple] = None) -> str:
    """Download audio from audio_url and transcribe it.

    Args:
        audio_url: Public or authenticated URL of the audio file.
        auth: Optional (username, password) tuple for HTTP Basic auth
              (used with Twilio recording URLs).

    Returns:
        Transcribed text, or empty string on failure.
    """
    if WHISPER_MODE == "api":
        return _transcribe_api(audio_url, auth)
    return _transcribe_local(audio_url, auth)


def transcribe_text(speech_result: str) -> str:
    """Pass-through when the telephony layer already provides transcribed text.

    Twilio's <Gather input="speech"> returns SpeechResult directly; this
    function normalises and lightly cleans it.
    """
    return speech_result.strip()


def _transcribe_api(audio_url: str, auth: Optional[tuple]) -> str:
    """Transcribe via OpenAI Whisper API."""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — cannot use Whisper API, trying local")
        return _transcribe_local(audio_url, auth)

    audio_path = _download_audio(audio_url, auth)
    if not audio_path:
        return ""

    try:
        import json
        import urllib.request as req_lib

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        boundary = "----WhisperBoundary"
        body_parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n',
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            audio_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(body_parts)
        request = req_lib.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with req_lib.urlopen(request, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get("text", "").strip()
    except Exception as exc:
        logger.warning("Whisper API transcription failed: %s", exc)
        return ""
    finally:
        try:
            audio_path.unlink()
        except Exception:
            pass


def _transcribe_local(audio_url: str, auth: Optional[tuple]) -> str:
    """Transcribe using the local openai-whisper library."""
    model = _get_local_model()
    if model is None:
        return ""

    audio_path = _download_audio(audio_url, auth)
    if not audio_path:
        return ""

    try:
        result = model.transcribe(str(audio_path))
        return result.get("text", "").strip()
    except Exception as exc:
        logger.warning("Local Whisper transcription failed: %s", exc)
        return ""
    finally:
        try:
            audio_path.unlink()
        except Exception:
            pass
