#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/workflow-builder"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/workflow-builder.env" ]]; then set -a; source "$AI_HOME/config/workflow-builder.env"; set +a; fi
exec python3 "$AGENT_HOME/workflow_builder.py"
