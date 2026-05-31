#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/customer-journey-mapper"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/customer-journey-mapper.env" ]]; then set -a; source "$AI_HOME/config/customer-journey-mapper.env"; set +a; fi
exec python3 "$AGENT_HOME/customer_journey_mapper.py"
