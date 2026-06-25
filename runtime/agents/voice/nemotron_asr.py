#!/usr/bin/env python3
"""Nemotron-3.5-ASR streaming runner (onnxruntime-genai, CPU int4 — no torch).

WAV file in -> transcript JSON on stdout. Invoked by
backend/services/voice/nemotron_asr.js. Mirrors kokoro_synth.py: self-contained +
GRACEFUL — if onnxruntime-genai / soundfile or the model files are absent it prints a
structured error to stderr and exits non-zero, so the Node side degrades cleanly
(the STT path falls back to whisper.cpp instead of crashing).

API mirrors the official onnxruntime-genai example examples/python/nemotron_speech.py
(model type "nemotron_speech": StreamingProcessor + RNN-T encoder/decoder/joint).

Models (downloaded once, owner action) live in:
  ~/.ai-employee/models/voice/nemotron/
    genai_config.json model_config.json audio_processor_config.json
    encoder.onnx(.data) decoder.onnx(.data) joint.onnx(.data) silero_vad.onnx
    tokenizer.json tokenizer_config.json vocab.txt

Install:  pip install onnxruntime-genai soundfile   (add --break-system-packages or a venv)
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Minimal verified language map from the onnxruntime-genai nemotron_speech example.
# "auto" (multilingual auto-detect) is the safe default; an explicit integer lang id
# may be passed via --lang-id for any of the model's 33+ languages.
LANG_TO_ID = {"auto": 101, "en": 0}

REQUIRED_FILES = ("genai_config.json", "encoder.onnx", "decoder.onnx", "joint.onnx", "tokenizer.json")


def _model_dir() -> Path:
    home = os.getenv("AI_HOME") or os.getenv("AI_EMPLOYEE_HOME") or os.path.join(os.path.expanduser("~"), ".ai-employee")
    return Path(os.getenv("VOICE_MODEL_ROOT") or os.path.join(home, "models", "voice")) / "nemotron"


def _fail(reason: str, code: int = 1):
    sys.stderr.write(json.dumps({"ok": False, "reason": reason}) + "\n")
    sys.exit(code)


def _resolve_lang_id(language: str, explicit_id) -> int:
    if explicit_id is not None:
        return int(explicit_id)
    return LANG_TO_ID.get((language or "auto").strip().lower(), LANG_TO_ID["auto"])


def _resample_mono(audio, sr, target_sr):
    import numpy as np  # noqa: PLC0415
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    if sr == target_sr or len(audio) == 0:
        return audio
    try:
        from scipy.signal import resample  # noqa: PLC0415
        return np.asarray(resample(audio, int(len(audio) * target_sr / sr)), dtype=np.float32)
    except Exception:  # noqa: BLE001 — linear fallback when scipy is absent
        n = max(1, int(len(audio) * target_sr / sr))
        idx = np.arange(n) * (len(audio) - 1) / max(1, n - 1)
        lo = np.floor(idx).astype(int)
        hi = np.minimum(lo + 1, len(audio) - 1)
        frac = (idx - lo).astype(np.float32)
        return (audio[lo] * (1 - frac) + audio[hi] * frac).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--language", default=os.getenv("VOICE_ASR_LANGUAGE", "auto"))
    ap.add_argument("--lang-id", type=int, default=None)
    ap.add_argument("--use-vad", default="false", choices=["true", "false"])
    args = ap.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        _fail(f"audio file not found: {audio_path}")

    mdir = Path(args.model_dir) if args.model_dir else _model_dir()
    missing = [f for f in REQUIRED_FILES if not (mdir / f).exists()]
    if missing:
        _fail(f"nemotron model files missing in {mdir}: {', '.join(missing)}")

    try:
        import numpy as np  # noqa: PLC0415
        import onnxruntime_genai as og  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _fail(f"onnxruntime-genai not installed ({exc}); run: pip install onnxruntime-genai")

    try:
        import soundfile as sf  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _fail(f"soundfile not installed ({exc}); run: pip install soundfile")

    try:
        cfg = json.loads((mdir / "genai_config.json").read_text())
        model_cfg = cfg.get("model", {})
        sample_rate = int(model_cfg.get("sample_rate", 16000))
        chunk_samples = int(model_cfg.get("chunk_samples", 8960))
    except Exception as exc:  # noqa: BLE001
        _fail(f"unable to read genai_config.json: {exc}")

    try:
        audio, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        audio = _resample_mono(audio, sr, sample_rate)
    except Exception as exc:  # noqa: BLE001
        _fail(f"unable to read audio: {exc}")

    if len(audio) == 0:
        _fail("audio is empty after decoding")

    lang_id = _resolve_lang_id(args.language, args.lang_id)
    try:
        config = og.Config(str(mdir))
        try:
            config.clear_providers()  # CPU-only by default; no GPU contention
        except Exception:  # noqa: BLE001 — older builds may lack clear_providers
            pass
        model = og.Model(config)
        processor = og.StreamingProcessor(model)
        processor.set_option("use_vad", args.use_vad)
        tokenizer = og.Tokenizer(model)
        tokenizer_stream = tokenizer.create_stream()
        params = og.GeneratorParams(model)
        generator = og.Generator(model, params)
        generator.set_runtime_option("lang_id", str(int(lang_id)))
    except Exception as exc:  # noqa: BLE001
        _fail(f"nemotron init failed: {exc}")

    def decode_tokens() -> str:
        text = ""
        while not generator.is_done():
            generator.generate_next_token()
            tokens = generator.get_next_tokens()
            if len(tokens) > 0:
                piece = tokenizer_stream.decode(tokens[0])
                if piece:
                    text += piece
        return text

    transcript = ""
    try:
        for i in range(0, len(audio), chunk_samples):
            chunk = np.asarray(audio[i:i + chunk_samples], dtype=np.float32)
            inputs = processor.process(chunk)
            if inputs is not None:
                generator.set_inputs(inputs)
                transcript += decode_tokens()
        inputs = processor.flush()
        if inputs is not None:
            generator.set_inputs(inputs)
            transcript += decode_tokens()
    except Exception as exc:  # noqa: BLE001
        _fail(f"transcription failed: {exc}")

    sys.stdout.write(json.dumps({
        "ok": True,
        "text": transcript.strip(),
        "lang_id": int(lang_id),
        "sample_rate": sample_rate,
    }) + "\n")


if __name__ == "__main__":
    main()
