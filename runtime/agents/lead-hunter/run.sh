#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/lead-hunter.env" ] && source "runtime/config/lead-hunter.env"
set +a
exec python3 "$AGENT_HOME/lead_hunter.py" "$@"
