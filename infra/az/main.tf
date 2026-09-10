data "azurerm_client_config" "current" {}
data "azuread_client_config" "current" {}

# -----------------------------------------------------------------------------
# 1. Resource Group
# -----------------------------------------------------------------------------
resource "azurerm_resource_group" "rg" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.common_tags
}

# -----------------------------------------------------------------------------
# 2. Monitoring: Log Analytics & Application Insights
# -----------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "log" {
  name                = local.log_analytics_workspace_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_application_insights" "appinsights" {
  name                = local.application_insights_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  workspace_id        = azurerm_log_analytics_workspace.log.id
  application_type    = "web"
  tags                = local.common_tags
}

# -----------------------------------------------------------------------------
# 3. Azure Storage: Account, CORS & Private Container
# -----------------------------------------------------------------------------
resource "azurerm_storage_account" "storage" {
  name                            = local.storage_account_name
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_tier                    = var.storage_account_tier
  account_replication_type        = var.storage_account_replication_type
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  public_network_access_enabled   = true
  allow_nested_items_to_be_public = false

  blob_properties {
    cors_rule {
      allowed_headers    = ["*"]
      allowed_methods    = ["PUT", "GET", "HEAD", "OPTIONS"]
      allowed_origins    = local.cors_origins
      exposed_headers    = ["*"]
      max_age_in_seconds = 3600
    }
  }

  tags = local.common_tags
}

resource "azurerm_storage_container" "submissions" {
  name                  = var.container_name
  storage_account_name  = azurerm_storage_account.storage.name
  container_access_type = "private"
}

# -----------------------------------------------------------------------------
# 4. App Service Plan (Consumption Linux)
# -----------------------------------------------------------------------------
resource "azurerm_service_plan" "plan" {
  name                = local.app_service_plan_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = local.common_tags
}

# -----------------------------------------------------------------------------
# 5. Azure Function App (Python v2)
# -----------------------------------------------------------------------------
resource "azurerm_linux_function_app" "function" {
  name                       = local.function_app_name
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  service_plan_id            = azurerm_service_plan.plan.id
  storage_account_name       = azurerm_storage_account.storage.name
  storage_account_access_key = azurerm_storage_account.storage.primary_access_key

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }

    cors {
      allowed_origins     = local.cors_origins
      support_credentials = true
    }
  }

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME"              = "python"
    "AzureWebJobsFeatureFlags"              = "EnableWorkerIndexing"
    "STORAGE_ACCOUNT_NAME"                  = azurerm_storage_account.storage.name
    "BLOB_CONTAINER_NAME"                   = azurerm_storage_container.submissions.name
    "DATAVERSE_URL"                         = var.dataverse_url
    "ENTRA_TENANT_ID"                       = local.tenant_id
    "API_AUDIENCE"                          = local.api_identifier_uri
    "BACKEND_API_CLIENT_ID"                 = azuread_application.upload_api.client_id
    "APPLICATIONINSIGHTS_CONNECTION_STRING" = azurerm_application_insights.appinsights.connection_string
  }

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# 6. RBAC Role Assignment: Function App Managed Identity -> Storage Blob Data Contributor
# -----------------------------------------------------------------------------
resource "azurerm_role_assignment" "storage_blob_contributor" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_linux_function_app.function.identity[0].principal_id
}
