#!/usr/bin/env bash
# Build and push the container image to ACR, then update the Foundry agent.
# Usage: ./scripts/deploy.sh <acr-name> <image-tag> [foundry-project-endpoint]

set -euo pipefail

ACR_NAME="${1:?ACR name required}"
IMAGE_TAG="${2:-latest}"
FOUNDRY_ENDPOINT="${3:-}"

IMAGE="${ACR_NAME}.azurecr.io/profile-agent:${IMAGE_TAG}"

echo "==> Logging into ACR: ${ACR_NAME}"
az acr login --name "${ACR_NAME}"

echo "==> Building image: ${IMAGE}"
docker build -t "${IMAGE}" .

echo "==> Pushing image: ${IMAGE}"
docker push "${IMAGE}"

echo "==> Image pushed successfully: ${IMAGE}"

if [ -n "${FOUNDRY_ENDPOINT}" ]; then
    echo "==> Updating Foundry agent..."
    python -m profile_agent.scripts.publish_to_foundry \
        --endpoint "${FOUNDRY_ENDPOINT}" \
        --image "${IMAGE}"
    echo "==> Foundry agent updated"
else
    echo "==> No Foundry endpoint provided — skipping agent update"
fi

echo "==> Done"
