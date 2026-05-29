#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FISH_SPEECH_HOME="${FISH_SPEECH_HOME:-$ROOT_DIR/runtime/vendor/fish-speech}"
FISH_SPEECH_PYTHON="${FISH_SPEECH_PYTHON:-python3}"
FISH_SPEECH_LISTEN="${FISH_SPEECH_LISTEN:-127.0.0.1:8080}"
FISH_SPEECH_CHECKPOINT="${FISH_SPEECH_CHECKPOINT:-checkpoints/s2-pro}"
FISH_SPEECH_DECODER="${FISH_SPEECH_DECODER:-checkpoints/s2-pro/codec.pth}"
FISH_SPEECH_DECODER_CONFIG="${FISH_SPEECH_DECODER_CONFIG:-modded_dac_vq}"
FISH_SPEECH_DEVICE="${FISH_SPEECH_DEVICE:-cuda}"
FISH_SPEECH_WORKERS="${FISH_SPEECH_WORKERS:-1}"

if [[ ! -d "$FISH_SPEECH_HOME" ]]; then
  echo "Fish Speech source not found: $FISH_SPEECH_HOME" >&2
  echo "Place the Fish Speech repo there, or set FISH_SPEECH_HOME=/path/to/fish-speech." >&2
  exit 2
fi

if [[ ! -f "$FISH_SPEECH_HOME/tools/api_server.py" ]]; then
  echo "Fish Speech API server not found at $FISH_SPEECH_HOME/tools/api_server.py" >&2
  exit 2
fi

cd "$FISH_SPEECH_HOME"

exec "$FISH_SPEECH_PYTHON" tools/api_server.py \
  --listen "$FISH_SPEECH_LISTEN" \
  --llama-checkpoint-path "$FISH_SPEECH_CHECKPOINT" \
  --decoder-checkpoint-path "$FISH_SPEECH_DECODER" \
  --decoder-config-name "$FISH_SPEECH_DECODER_CONFIG" \
  --device "$FISH_SPEECH_DEVICE" \
  --workers "$FISH_SPEECH_WORKERS"
