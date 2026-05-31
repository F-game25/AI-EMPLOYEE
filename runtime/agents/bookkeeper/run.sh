#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/bookkeeper.env" ] && source "runtime/config/bookkeeper.env"
set +a
exec python3 "$AGENT_HOME/bookkeeper.py" "$@"
