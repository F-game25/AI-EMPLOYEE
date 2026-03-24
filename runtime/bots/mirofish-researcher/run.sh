#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/mirofish-researcher"

if [[ -f "$AI_HOME/config/mirofish-researcher.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/mirofish-researcher.env"
  set +a
fi

exec python3 "$BOT_HOME/researcher.py"
