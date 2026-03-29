#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
BOT_HOME="$AI_HOME/bots/qa-tester"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/qa-tester.env" ]]; then set -a; source "$AI_HOME/config/qa-tester.env"; set +a; fi
python3 "$BOT_HOME/qa_tester.py"
