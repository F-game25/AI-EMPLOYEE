#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/content-master.env" ] && source "runtime/config/content-master.env"
set +a
exec python3 "$AGENT_HOME/content_master.py" "$@"
