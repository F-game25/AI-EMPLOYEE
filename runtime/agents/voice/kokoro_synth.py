#!/usr/bin/env python3
"""Kokoro 82M TTS synth (kokoro-onnx — no torch). Text -> WAV on stdout.

Invoked by backend/services/voice/kokoro.js. Self-contained + GRACEFUL: if the
package or model files are not installed it prints a structured error to stderr and
exits non-zero, so the Node side degrades cleanly (the teammate falls back to text).

Models (downloaded once, owner action) live in:
  ~/.ai-employee/models/voice/kokoro/{kokoro-v1.0.onnx, voices-v1.0.bin}

Install:  pip install kokoro-onnx soundfile   (add --break-system-packages or a venv)
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path


def _model_dir() -> Path:
    home = os.getenv("AI_HOME") or os.path.join(os.path.expanduser("~"), ".ai-employee")
    return Path(os.getenv("VOICE_MODEL_ROOT") or os.path.join(home, "models", "voice")) / "kokoro"


def _fail(reason: str, code: int = 1):
    sys.stderr.write(json.dumps({"ok": False, "reason": reason}) + "\n")
    sys.exit(code)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--voice", default=os.getenv("KOKORO_VOICE", "af_sarah"))
    ap.add_argument("--speed", type=float, default=float(os.getenv("KOKORO_SPEED", "1.0")))
    ap.add_argument("--lang", default=os.getenv("KOKORO_LANG", "en-us"))
    ap.add_argument("--out", default="-")  # '-' = stdout
    args = ap.parse_args()

    text = (args.text or "").strip()
    if not text:
        _fail("empty text")

    try:
        from kokoro_onnx import Kokoro  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _fail(f"kokoro-onnx not installed ({exc}); run: pip install kokoro-onnx soundfile")

    mdir = _model_dir()
    onnx = mdir / "kokoro-v1.0.onnx"
    voices = mdir / "voices-v1.0.bin"
    if not onnx.exists() or not voices.exists():
        _fail(f"kokoro model files missing in {mdir} (kokoro-v1.0.onnx + voices-v1.0.bin)")

    try:
        kokoro = Kokoro(str(onnx), str(voices))
        samples, sample_rate = kokoro.create(
            text, voice=args.voice, speed=max(0.5, min(2.0, args.speed)), lang=args.lang)
    except Exception as exc:  # noqa: BLE001
        _fail(f"synthesis failed: {exc}")

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    data = buf.getvalue()
    if args.out == "-":
        sys.stdout.buffer.write(data)
    else:
        Path(args.out).write_bytes(data)
    sys.stderr.write(json.dumps({"ok": True, "bytes": len(data), "sample_rate": sample_rate}) + "\n")


if __name__ == "__main__":
    main()
