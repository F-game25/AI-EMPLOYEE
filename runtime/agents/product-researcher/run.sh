#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/product-researcher.env" ] && source "runtime/config/product-researcher.env"
set +a
exec python3 "$AGENT_HOME/product_researcher.py" "$@"
