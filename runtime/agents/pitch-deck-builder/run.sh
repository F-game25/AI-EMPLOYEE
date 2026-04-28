#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/pitch-deck-builder"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/pitch-deck-builder.env" ]]; then set -a; source "$AI_HOME/config/pitch-deck-builder.env"; set +a; fi
exec python3 "$AGENT_HOME/pitch_deck_builder.py"
