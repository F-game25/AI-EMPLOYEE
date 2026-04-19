#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

if [[ -f backend.pid ]]; then
  kill "$(cat backend.pid)" 2>/dev/null || true
  rm -f backend.pid
fi

if [[ -f worker.pid ]]; then
  kill "$(cat worker.pid)" 2>/dev/null || true
  rm -f worker.pid
fi

echo "System stopped."
