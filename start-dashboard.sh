#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Legacy multi-port dashboard launcher disabled."
echo "Starting single-port runtime on http://127.0.0.1:8787"
exec "$ROOT/runtime/start.sh"
