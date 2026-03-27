#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/whatsapp-webhook"

if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi

if [[ -f "$AI_HOME/config/whatsapp-webhook.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/whatsapp-webhook.env"
  set +a
fi

exec python3 "$BOT_HOME/webhook_server.py"
