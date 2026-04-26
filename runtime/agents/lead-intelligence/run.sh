#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/lead-intelligence"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/lead-intelligence.env" ]]; then set -a; source "$AI_HOME/config/lead-intelligence.env"; set +a; fi
exec python3 "$AGENT_HOME/lead_scoring_agent.py"
