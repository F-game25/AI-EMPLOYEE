#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/support-bot.env" ] && source "runtime/config/support-bot.env"
set +a
exec python3 "$AGENT_HOME/support_bot.py" "$@"
