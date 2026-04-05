#!/usr/bin/env bash
set -euo pipefail
AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
AGENT_HOME="$AI_HOME/agents/recruiter"
if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
if [[ -f "$AI_HOME/config/recruiter.env" ]]; then set -a; source "$AI_HOME/config/recruiter.env"; set +a; fi
python3 "$AGENT_HOME/recruiter.py"
