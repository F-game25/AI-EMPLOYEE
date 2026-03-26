#!/usr/bin/env bash
# Start the feedback-loop service
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
ENV_FILE="$AI_HOME/.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

exec python3 "$SCRIPT_DIR/feedback_loop.py" "$@"
