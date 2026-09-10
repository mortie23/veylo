#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../app/veylo/file-upload" && pwd)"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-vey-portal-dev-01}"
FUNCTION_APP="${FUNCTION_APP:-func-vey-portal-dev-up-01}"

echo "=== Deploying Azure Function App: ${FUNCTION_APP} ==="

cd "${APP_DIR}"
ZIP_PATH="/tmp/func-deploy-${FUNCTION_APP}.zip"
rm -f "${ZIP_PATH}"

echo "Packaging Python application..."
zip -q -r "${ZIP_PATH}" . -x ".venv/*" "tests/*" ".pytest_cache/*" "*__pycache__*" "*.pyc" "local.settings.json" "pyproject.toml" "uv.lock" ".python-version"

echo "Uploading and building remotely on Azure (Oryx)..."
az functionapp deployment source config-zip \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${FUNCTION_APP}" \
  --src "${ZIP_PATH}" \
  --build-remote true

rm -f "${ZIP_PATH}"

echo "Syncing function triggers with worker indexing..."
az resource invoke-action --action syncfunctiontriggers \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${FUNCTION_APP}" \
  --resource-type "Microsoft.Web/sites" > /dev/null 2>&1 || true

echo "=== Deployment complete! Registered functions: ==="
az functionapp function list \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${FUNCTION_APP}" \
  --query "[].name" -o tsv
