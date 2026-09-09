output "resource_group_name" {
  description = "Name of the provisioned Azure Resource Group"
  value       = azurerm_resource_group.rg.name
}

output "storage_account_name" {
  description = "Name of the storage account hosting file submissions"
  value       = azurerm_storage_account.storage.name
}

output "storage_container_name" {
  description = "Name of the private blob container for uploads"
  value       = azurerm_storage_container.submissions.name
}

output "storage_primary_blob_endpoint" {
  description = "Primary blob endpoint URL"
  value       = azurerm_storage_account.storage.primary_blob_endpoint
}

output "function_app_name" {
  description = "Name of the Azure Function App"
  value       = azurerm_linux_function_app.function.name
}

output "function_app_default_hostname" {
  description = "Default hostname of the Azure Function App"
  value       = azurerm_linux_function_app.function.default_hostname
}

output "function_app_url" {
  description = "Root URL of the Azure Function App"
  value       = "https://${azurerm_linux_function_app.function.default_hostname}"
}

output "function_principal_id" {
  description = "System-Assigned Managed Identity Principal ID (for Dataverse Application User assignment)"
  value       = azurerm_linux_function_app.function.identity[0].principal_id
}

output "backend_api_client_id" {
  description = "Entra ID Application (Client) ID of the Backend API"
  value       = azuread_application.upload_api.client_id
}

output "backend_api_identifier_uri" {
  description = "Entra ID Identifier URI for the Backend API"
  value       = local.api_identifier_uri
}

output "backend_api_scope" {
  description = "Exposed OAuth2 scope name for file upload"
  value       = "File.Upload"
}

output "backend_api_scope_uri" {
  description = "Full URI of the OAuth2 scope to request from MSAL.js"
  value       = "${local.api_identifier_uri}/File.Upload"
}

output "frontend_spa_client_id" {
  description = "Entra ID Application (Client) ID for Power Pages MSAL.js SPA"
  value       = azuread_application.portal_spa.client_id
}

output "entra_tenant_id" {
  description = "Entra ID Tenant ID used for authentication"
  value       = local.tenant_id
}

output "application_insights_connection_string" {
  description = "Application Insights Connection String"
  value       = azurerm_application_insights.appinsights.connection_string
  sensitive   = true
}
