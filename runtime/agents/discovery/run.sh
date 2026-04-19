#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/discovery"

if [[ -f "$AI_HOME/config/discovery.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$AI_HOME/config/discovery.env"
  set +a
fi

exec python3 "$AGENT_HOME/discovery.py"
