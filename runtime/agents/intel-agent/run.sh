#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/intel-agent.env" ] && source "runtime/config/intel-agent.env"
set +a
exec python3 "$AGENT_HOME/intel_agent.py" "$@"
