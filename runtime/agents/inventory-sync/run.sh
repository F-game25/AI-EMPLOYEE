#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/inventory-sync.env" ] && source "runtime/config/inventory-sync.env"
set +a
exec python3 "$AGENT_HOME/inventory_sync.py" "$@"
