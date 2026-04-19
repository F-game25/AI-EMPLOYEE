#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_START="$ROOT/runtime/start.sh"

echo "Legacy multi-port dashboard launcher disabled."
echo "Starting single-port runtime on http://127.0.0.1:8787"
if [[ ! -f "$RUNTIME_START" ]]; then
  echo "Error: runtime launcher not found at $RUNTIME_START" >&2
  exit 1
fi
if [[ ! -x "$RUNTIME_START" ]]; then
  chmod +x "$RUNTIME_START"
fi
exec "$RUNTIME_START"
