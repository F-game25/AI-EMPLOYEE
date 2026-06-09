#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
[[ -f "$AI_HOME/.env" ]] && { set -a; source "$AI_HOME/.env"; set +a; }
[[ -f "$AI_HOME/config/react-coder.env" ]] && { set -a; source "$AI_HOME/config/react-coder.env"; set +a; }
exec python3 -m agents.react_coder.react_coder "$@"
