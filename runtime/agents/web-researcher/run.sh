#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/web-researcher"

# Load global .env (TAVILY_API_KEY, NEWS_API_KEY, etc.)
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi

# Load bot-specific env
if [[ -f "$AI_HOME/config/web-researcher.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/web-researcher.env"
  set +a
fi

exec python3 "$AGENT_HOME/web_researcher.py"
