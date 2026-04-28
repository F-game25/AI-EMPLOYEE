#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/data-analyst.env" ] && source "runtime/config/data-analyst.env"
set +a
exec python3 "$AGENT_HOME/data_analyst.py" "$@"
