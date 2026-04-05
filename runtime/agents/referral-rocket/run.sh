#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/referral-rocket"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/referral-rocket.env" ]]; then set -a; source "$AI_HOME/config/referral-rocket.env"; set +a; fi
python3 "$AGENT_HOME/referral_rocket.py"
