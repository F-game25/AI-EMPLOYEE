#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/company-manager"

if [[ -f "$AI_HOME/.env" ]]; then
  set -a; source "$AI_HOME/.env"; set +a
fi

exec python3 "$AGENT_HOME/company_manager.py"
