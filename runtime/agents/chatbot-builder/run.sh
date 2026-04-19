#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/chatbot-builder"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/chatbot-builder.env" ]]; then set -a; source "$AI_HOME/config/chatbot-builder.env"; set +a; fi
exec python3 "$AGENT_HOME/chatbot_builder.py"
