#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/financial-deepsearch"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/financial-deepsearch.env" ]]; then set -a; source "$AI_HOME/config/financial-deepsearch.env"; set +a; fi
python3 "$BOT_HOME/financial_deepsearch.py"
