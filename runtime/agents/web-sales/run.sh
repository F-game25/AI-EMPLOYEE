#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/web-sales.env" ] && source "runtime/config/web-sales.env"
set +a
exec python3 "$AGENT_HOME/web_sales.py" "$@"
