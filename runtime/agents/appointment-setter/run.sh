#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/appointment-setter"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/appointment-setter.env" ]]; then set -a; source "$AI_HOME/config/appointment-setter.env"; set +a; fi
exec python3 "$AGENT_HOME/appointment_setter.py"
