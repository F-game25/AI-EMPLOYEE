#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/social-guru.env" ] && source "runtime/config/social-guru.env"
set +a
exec python3 "$AGENT_HOME/social_guru.py" "$@"
