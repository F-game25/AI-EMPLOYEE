#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/growth-hacker"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/growth-hacker.env" ]]; then set -a; source "$AI_HOME/config/growth-hacker.env"; set +a; fi
exec python3 "$AGENT_HOME/growth_hacker.py"
