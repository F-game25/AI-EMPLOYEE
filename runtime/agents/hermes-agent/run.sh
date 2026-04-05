#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/hermes-agent"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/hermes-agent.env" ]]; then set -a; source "$AI_HOME/config/hermes-agent.env"; set +a; fi
python3 "$AGENT_HOME/hermes_agent.py"
