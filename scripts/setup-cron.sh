#!/usr/bin/env bash
# AI Employee — Cron Setup
# Adds a cron job to run sync.sh every 30 minutes.
# Usage: bash scripts/setup-cron.sh

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYNC_SCRIPT="$REPO_DIR/scripts/sync.sh"
CRON_LINE="*/30 * * * * bash $SYNC_SCRIPT >> ~/.ai-employee/logs/sync-cron.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -qF "$SYNC_SCRIPT"; then
  echo "Cron job already exists. Nothing changed."
  echo "   To view:   crontab -l"
  echo "   To remove: crontab -e"
else
  # Add to crontab
  ( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -
  echo "✅ Cron job added — syncs every 30 minutes automatically"
  echo "   To view:   crontab -l"
  echo "   To remove: crontab -e"
fi
