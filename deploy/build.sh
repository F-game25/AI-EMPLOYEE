#!/usr/bin/env bash
# Build Docker images for Aeternus Nexus.
set -euo pipefail

REGISTRY="${REGISTRY:-aeternus}"
TAG="${TAG:-$(git describe --tags --always --dirty 2>/dev/null || echo 'latest')}"
PUSH="${PUSH:-0}"

echo "Building images (tag: ${TAG})"

docker build -t "${REGISTRY}/nexus-node:${TAG}"   -f Dockerfile.node   .
docker build -t "${REGISTRY}/nexus-python:${TAG}" -f Dockerfile.python .

if [[ "${PUSH}" == "1" ]]; then
  echo "Pushing images..."
  docker push "${REGISTRY}/nexus-node:${TAG}"
  docker push "${REGISTRY}/nexus-python:${TAG}"
fi

echo "Done. Image tag: ${TAG}"
