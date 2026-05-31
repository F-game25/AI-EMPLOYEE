#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/product-scout.env" ] && source "runtime/config/product-scout.env"
set +a
exec python3 "$AGENT_HOME/product_scout.py" "$@"
