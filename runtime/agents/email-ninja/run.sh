#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/email-ninja.env" ] && source "runtime/config/email-ninja.env"
set +a
exec python3 "$AGENT_HOME/email_ninja.py" "$@"
