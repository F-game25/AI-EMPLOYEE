#!/usr/bin/env bash
# Delegates to the repo root stop.sh — the single authoritative stop script.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
exec bash "$REPO_ROOT/stop.sh" "$@"
