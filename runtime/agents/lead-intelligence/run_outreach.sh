#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/lead-intelligence"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/outreach-agent.env" ]]; then set -a; source "$AI_HOME/config/outreach-agent.env"; set +a; fi
python3 "$AGENT_HOME/outreach_agent.py"
