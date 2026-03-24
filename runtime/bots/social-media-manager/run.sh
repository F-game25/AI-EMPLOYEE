#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/social-media-manager"

# Load global .env
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi

# Load bot-specific env
if [[ -f "$AI_HOME/config/social-media-manager.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/social-media-manager.env"
  set +a
fi

python3 "$BOT_HOME/social_media_manager.py"
