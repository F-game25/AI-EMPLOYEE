#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/competitor-watch"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/competitor-watch.env" ]]; then set -a; source "$AI_HOME/config/competitor-watch.env"; set +a; fi
exec python3 "$AGENT_HOME/competitor_watch.py"
