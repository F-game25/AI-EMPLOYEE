#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/qa-tester"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/qa-tester.env" ]]; then set -a; source "$AI_HOME/config/qa-tester.env"; set +a; fi
exec python3 "$AGENT_HOME/qa_tester.py"
