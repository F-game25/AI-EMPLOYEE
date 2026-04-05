#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/cold-outreach-assassin"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/cold-outreach-assassin.env" ]]; then set -a; source "$AI_HOME/config/cold-outreach-assassin.env"; set +a; fi
python3 "$AGENT_HOME/cold_outreach_assassin.py"
