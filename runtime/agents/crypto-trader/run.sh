#!/bin/bash
set -a
[ -f "$AI_HOME/.env" ] && source "$AI_HOME/.env"
[ -f "runtime/config/crypto-trader.env" ] && source "runtime/config/crypto-trader.env"
set +a
exec python3 "$AGENT_HOME/crypto_trader.py" "$@"
