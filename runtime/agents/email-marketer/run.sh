#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/email-marketer.env" ] && source "runtime/config/email-marketer.env"
set +a
exec python3 "$AGENT_HOME/email_marketer.py" "$@"
