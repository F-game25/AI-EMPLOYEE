#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/ollama-agent"

# Load global .env for shared vars (OLLAMA_HOST, OLLAMA_MODEL, etc.)
if [[ -f "$AI_HOME/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/.env"
  set +a
fi

# Load bot-specific env (overrides if set)
if [[ -f "$AI_HOME/config/ollama-agent.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/ollama-agent.env"
  set +a
fi

exec python3 "$AGENT_HOME/ollama_agent.py"
