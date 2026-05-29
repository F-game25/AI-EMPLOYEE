#!/usr/bin/env bash
# Local-only Neo4j for the neural-brain graph (no docker-compose dependency).
# Idempotent: starts the container if missing, restarts it if stopped. Bound to
# 127.0.0.1 only. Data persists under ~/.ai-employee/neo4j. The system runs fine
# without this (native SQLite floor) — start.sh calls it best-effort.
set -euo pipefail

NAME="ai-employee-neo4j"
IMAGE="neo4j:5-community"
PASS="${NEO4J_PASSWORD:-neuralbrain}"
DATA="${HOME}/.ai-employee/neo4j/data"
LOGS="${HOME}/.ai-employee/neo4j/logs"

command -v docker >/dev/null 2>&1 || { echo "[neo4j] docker not present — skipping (native graph floor stays active)"; exit 0; }
docker info >/dev/null 2>&1 || { echo "[neo4j] docker daemon unreachable — skipping"; exit 0; }

# Already running?
if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "[neo4j] already running"; exit 0
fi
# Exists but stopped?
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "[neo4j] starting existing container"; docker start "$NAME" >/dev/null; exit 0
fi

mkdir -p "$DATA" "$LOGS"
echo "[neo4j] creating container (first run pulls ${IMAGE}, ~600MB)…"
docker run -d --name "$NAME" --restart unless-stopped \
  -p 127.0.0.1:7474:7474 -p 127.0.0.1:7687:7687 \
  -e NEO4J_AUTH="neo4j/${PASS}" \
  -e NEO4J_server_memory_heap_max__size="512m" \
  -e NEO4J_server_memory_pagecache_size="256m" \
  -v "${DATA}:/data" -v "${LOGS}:/logs" \
  "$IMAGE" >/dev/null
echo "[neo4j] container started (accepts connections in ~20-40s)"
