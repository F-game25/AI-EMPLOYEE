# Voice System — Implementation Plan

**Goal:** a genuinely good, fully UI-customizable voice system so the teammate can
**hear** and **speak**, the **avatar (eye)** reacts, and the same engine powers
**external uses** — call automation and video narration.

## Confirmed models (from the reference)
- **Hear (STT/ASR):** `nvidia/nemotron-3.5-asr-streaming-0.6b` — 0.6B, **CPU-only**,
  40+ languages, real-time **streaming**, 2.5× faster than peers. Use the lightweight
  **ONNX int4** build `onnx-community/nemotron-3.5-asr-streaming-0.6b-onnx-int4`
  (no torch) for a small, fast, GPU-free install.
- **Speak (TTS):** `Kokoro 82M` (your choice) — natural, tiny, CPU/GPU, no torch via
  `kokoro-onnx`.

Both run on the existing voice subsystem (`backend/services/voice/*`,
`voice_runtime_manager`, companion `_speak`, `voiceStore`, avatar engine).

## Architecture
```
mic ─► Nemotron-ASR (stream) ─► transcript ─► Companion Gateway ─► reply text
                                                   │
avatar(eye): listening ◄── thinking ◄── speaking ─┤
                                                   ▼
                                          Kokoro-TTS ─► audio ─► playback
```
- **Avatar (eye)** is driven by voice phase: `listening` (ASR active) → `thinking`
  (companion) → `speaking` (TTS). `voiceStore` + `avatar_state_engine` already model
  these states; wire the ASR/TTS lifecycle to them.
- **One voice config** (UI-customizable) is the single source of truth for every
  surface (chat voice, call automation, narration).

## Phases
**P1 — Customizable voice config + adapters (foundation).**
- `runtime/config/voice_settings.json` + API (`GET/PATCH /api/voice/settings`):
  engine choice (asr: nemotron|whisper, tts: kokoro|piper|fish), Kokoro **voice**,
  speed, pitch, language, auto-listen, push-to-talk, barge-in. Tenant-scoped.
- Frontend **Voice settings** panel (live preview "Test voice" button).
- Engine adapters (graceful, no-crash if model absent): `nemotron_asr.js`
  (ONNX int4) + `kokoro.js` (kokoro-onnx). Install via the manager's downloader.

**P2 — Live voice chat + avatar.**
- Frontend mic capture → stream to Nemotron ASR → live transcript (captions) →
  companion → Kokoro audio playback. Avatar(eye) reacts per phase. Barge-in.

**P3 — External voice system.**
- **Narration:** `POST /api/voice/narrate { text, voice }` → MP3/WAV artifact (shows
  in the AI Output screen; pairs with HyperFrames video).
- **Call automation:** a session API (ASR↔companion↔TTS loop) behind owner-gating +
  the egress guard, deny-by-default.

## Security / hardware
- CPU-only ASR + tiny TTS → no contention with Qwythos on the 8 GB GPU.
- Models live in `~/.ai-employee/models/voice/` (downloaded, owner-gated).
- External call/narration = outward-facing → approval-gated, egress-guarded, audited.
- All processing local by default; nothing leaves the box unless a call endpoint is
  explicitly enabled.

## Install (owner action, like the Ollama upgrade)
```
pip install kokoro-onnx onnxruntime soundfile   # TTS (no torch)
# ASR ONNX int4 + Kokoro model/voices auto-download to ~/.ai-employee/models/voice/
```
