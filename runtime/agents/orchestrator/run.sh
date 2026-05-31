#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/orchestrator.env" ] && source "runtime/config/orchestrator.env"
set +a
exec python3 "$AGENT_HOME/orchestrator.py" "$@"
