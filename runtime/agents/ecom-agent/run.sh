#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/ecom-agent"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/ecom-agent.env" ]]; then set -a; source "$AI_HOME/config/ecom-agent.env"; set +a; fi
python3 "$AGENT_HOME/ecom_agent.py"
