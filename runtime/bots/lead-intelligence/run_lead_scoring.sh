#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/lead-intelligence"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/lead-scoring-agent.env" ]]; then set -a; source "$AI_HOME/config/lead-scoring-agent.env"; set +a; fi
python3 "$BOT_HOME/lead_scoring_agent.py"
