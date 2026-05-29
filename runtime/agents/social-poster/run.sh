#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/social-poster.env" ] && source "runtime/config/social-poster.env"
set +a
exec python3 "$AGENT_HOME/social_poster.py" "$@"
