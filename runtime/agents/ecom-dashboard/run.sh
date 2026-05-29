#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/ecom-dashboard.env" ] && source "runtime/config/ecom-dashboard.env"
set +a
exec python3 "$AGENT_HOME/ecom_dashboard.py" "$@"
