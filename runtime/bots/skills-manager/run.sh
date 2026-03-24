#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/skills-manager"

if [[ -f "$AI_HOME/config/skills-manager.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/skills-manager.env"
  set +a
fi

exec python3 "$BOT_HOME/skills_manager.py"
