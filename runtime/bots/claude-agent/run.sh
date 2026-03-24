#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/claude-agent"

# Load global .env for ANTHROPIC_API_KEY
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi

# Load bot-specific env (overrides if set)
if [[ -f "$AI_HOME/config/claude-agent.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/claude-agent.env"
  set +a
fi

python3 "$BOT_HOME/claude_agent.py"
