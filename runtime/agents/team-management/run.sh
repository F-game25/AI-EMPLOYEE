#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/team-management"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/team-management.env" ]]; then set -a; source "$AI_HOME/config/team-management.env"; set +a; fi
exec python3 "$AGENT_HOME/team_management.py"
