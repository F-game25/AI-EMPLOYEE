#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/website-builder"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/website-builder.env" ]]; then set -a; source "$AI_HOME/config/website-builder.env"; set +a; fi
exec python3 "$AGENT_HOME/website_builder.py"
