#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/bot-dev.env" ] && source "runtime/config/bot-dev.env"
set +a
exec python3 "$AGENT_HOME/bot_dev.py" "$@"
