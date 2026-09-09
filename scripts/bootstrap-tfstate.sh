#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Bootstrap Subscription-Level Remote Terraform State Storage
# -----------------------------------------------------------------------------
# Creates a shared, non-app-specific Resource Group, Storage Account,
# and private blob container for Terraform state management across workloads.
# Specific workloads (e.g. Veylo) partition their state at the key level.
# -----------------------------------------------------------------------------

RESOURCE_GROUP_NAME="${1:-rg-mgmt-tfstate-01}"
STORAGE_ACCOUNT_NAME="${2:-stcoretfstate01}"
CONTAINER_NAME="${3:-tfstate}"
LOCATION="${4:-australiaeast}"

echo "================================================================="
echo " Bootstrapping Shared Terraform Remote State Backend"
echo " Resource Group  : $RESOURCE_GROUP_NAME"
echo " Storage Account : $STORAGE_ACCOUNT_NAME"
echo " Blob Container  : $CONTAINER_NAME"
echo " Region          : $LOCATION"
echo "================================================================="

# 1. Create Shared Management Resource Group
echo "Creating Management Resource Group..."
az group create \
  --name "$RESOURCE_GROUP_NAME" \
  --location "$LOCATION" \
  --tags Tier=Management Purpose=TerraformState ManagedBy=Bootstrap Scope=Shared \
  --output table

# 2. Create Shared Storage Account
echo "Creating Shared State Storage Account..."
az storage account create \
  --name "$STORAGE_ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP_NAME" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --encryption-services blob \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --tags Tier=Management Purpose=TerraformState Scope=Shared \
  --output table

# 3. Enable Blob Versioning (preserves state history for recovery)
echo "Enabling Blob Versioning on state storage account..."
az storage account blob-service-properties update \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --resource-group "$RESOURCE_GROUP_NAME" \
  --enable-versioning true \
  --output none

# 4. Assign Storage Blob Data Contributor role to the signed-in identity
echo "Granting current identity Entra ID data-plane access (Storage Blob Data Contributor)..."
CURRENT_USER_OBJECT_ID=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)
ASSIGNEE_TYPE="User"

if [ -z "$CURRENT_USER_OBJECT_ID" ]; then
  # Fallback for Service Principal / Managed Identity (e.g. CI/CD automation)
  CURRENT_USER_OBJECT_ID=$(az account show --query user.name -o tsv 2>/dev/null || true)
  ASSIGNEE_TYPE="ServicePrincipal"
fi

STORAGE_ACCOUNT_ID=$(az storage account show --name "$STORAGE_ACCOUNT_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query id -o tsv)

if [ -n "$CURRENT_USER_OBJECT_ID" ]; then
  az role assignment create \
    --assignee "$CURRENT_USER_OBJECT_ID" \
    --assignee-principal-type "$ASSIGNEE_TYPE" \
    --role "Storage Blob Data Contributor" \
    --scope "$STORAGE_ACCOUNT_ID" \
    --output none || true
fi

# 5. Create Blob Container for tfstate
echo "Creating '$CONTAINER_NAME' blob container..."
# Attempt Entra ID login auth first; fallback to storage account key if RBAC is still propagating
if ! az storage container create \
  --name "$CONTAINER_NAME" \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --auth-mode login \
  --output table 2>/dev/null; then
  echo "Note: Entra ID role assignment is still replicating to data-plane; using management key..."
  az storage container create \
    --name "$CONTAINER_NAME" \
    --account-name "$STORAGE_ACCOUNT_NAME" \
    --auth-mode key \
    --output table
fi

echo ""
echo "================================================================="
echo " Bootstrap Complete! Shared remote state backend is ready."
echo " Specific projects should store state with their own path prefix,"
echo " e.g. key = 'veylo/portal/dev.tfstate'"
echo "================================================================="
