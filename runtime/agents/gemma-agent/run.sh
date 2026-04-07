#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/gemma-agent"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/gemma-agent.env" ]]; then set -a; source "$AI_HOME/config/gemma-agent.env"; set +a; fi
python3 "$AGENT_HOME/gemma_agent.py"
