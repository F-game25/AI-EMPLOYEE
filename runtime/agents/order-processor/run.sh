#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/order-processor.env" ] && source "runtime/config/order-processor.env"
set +a
exec python3 "$AGENT_HOME/order_processor.py" "$@"
