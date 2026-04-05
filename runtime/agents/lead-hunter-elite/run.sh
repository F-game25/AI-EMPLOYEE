#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/lead-hunter-elite"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/lead-hunter-elite.env" ]]; then set -a; source "$AI_HOME/config/lead-hunter-elite.env"; set +a; fi
python3 "$AGENT_HOME/lead_hunter_elite.py"
