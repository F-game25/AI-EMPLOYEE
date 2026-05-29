#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/creative-studio.env" ] && source "runtime/config/creative-studio.env"
set +a
exec python3 "$AGENT_HOME/creative_studio.py" "$@"
