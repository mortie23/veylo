# -----------------------------------------------------------------------------
# Remote State Storage Backend for AzureRM
# -----------------------------------------------------------------------------
# Backed by a subscription-wide shared management Storage Account.
# Workload-specific state is partitioned by key prefix (veylo/portal/dev.tfstate).
# Authentication uses the active Azure CLI session via Entra ID (RBAC).
# -----------------------------------------------------------------------------
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-mgmt-tfstate-01"
    storage_account_name = "stcoretfstate01"
    container_name       = "tfstate"
    key                  = "veylo/portal/dev.tfstate"
    use_azuread_auth     = true
  }
}
