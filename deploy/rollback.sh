#!/usr/bin/env bash
# Roll back to the previous Helm release revision.
set -euo pipefail

NAMESPACE="${NAMESPACE:-nexus}"
RELEASE="${RELEASE:-aeternus-nexus}"
REVISION="${REVISION:-0}"   # 0 = previous

echo "Rolling back ${RELEASE} in ${NAMESPACE} (revision: ${REVISION:-previous})"

if [[ "${REVISION}" == "0" ]]; then
  helm rollback "${RELEASE}" --namespace "${NAMESPACE}" --wait --timeout 5m
else
  helm rollback "${RELEASE}" "${REVISION}" --namespace "${NAMESPACE}" --wait --timeout 5m
fi

echo "Rollback complete."
helm history "${RELEASE}" --namespace "${NAMESPACE}" --max 5
