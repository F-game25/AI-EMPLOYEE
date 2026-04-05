#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/partnership-matchmaker"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/partnership-matchmaker.env" ]]; then set -a; source "$AI_HOME/config/partnership-matchmaker.env"; set +a; fi
python3 "$AGENT_HOME/partnership_matchmaker.py"
