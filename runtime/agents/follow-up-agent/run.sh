#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/follow-up-agent"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/follow-up-agent.env" ]]; then set -a; source "$AI_HOME/config/follow-up-agent.env"; set +a; fi
python3 "$AGENT_HOME/follow_up_agent.py"
