#!/usr/bin/env bash
# AI Employee — Auto-Sync Watcher
# Usage: bash scripts/sync-watch.sh [interval_minutes]
# Default interval: 30 minutes
# Press Ctrl+C to stop.

INTERVAL="${1:-30}"
echo "Auto-sync every ${INTERVAL} minutes. Press Ctrl+C to stop."

while true; do
  bash "$(dirname "$0")/sync.sh"
  echo "Next sync in ${INTERVAL} minutes..."
  sleep $(( INTERVAL * 60 ))
done
