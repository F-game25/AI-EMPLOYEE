#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/finance-wizard"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/finance-wizard.env" ]]; then set -a; source "$AI_HOME/config/finance-wizard.env"; set +a; fi
exec python3 "$AGENT_HOME/finance_wizard.py"
