#!/usr/bin/env bash
# Deploy Aeternus Nexus via Helm.
set -euo pipefail

NAMESPACE="${NAMESPACE:-nexus}"
RELEASE="${RELEASE:-aeternus-nexus}"
VALUES="${VALUES:-helm/aeternus-nexus/values.yaml}"
VALUES_PROD="${VALUES_PROD:-helm/aeternus-nexus/values-prod.yaml}"
TAG="${TAG:-latest}"

echo "Deploying ${RELEASE} to namespace ${NAMESPACE} (image tag: ${TAG})"

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install "${RELEASE}" ./helm/aeternus-nexus \
  --namespace "${NAMESPACE}" \
  --values "${VALUES}" \
  $([ -f "${VALUES_PROD}" ] && echo "--values ${VALUES_PROD}") \
  --set "image.tag=${TAG}" \
  --wait \
  --timeout 10m

echo "Running smoke tests..."
bash deploy/smoke-test.sh && echo "Smoke tests PASSED" || {
  echo "Smoke tests FAILED — rolling back"
  bash deploy/rollback.sh
  exit 1
}

echo "Deployment complete."
