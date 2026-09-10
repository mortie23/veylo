locals {
  name_prefix = "vey"

  resource_group_name          = "rg-vey-${var.app_name}-${var.environment}-${var.instance_seq}"
  app_service_plan_name        = "plan-vey-${var.app_name}-${var.environment}-${var.instance_seq}"
  function_app_name            = "func-vey-${var.app_name}-${var.environment}-${var.workload_unit}-${var.instance_seq}"
  storage_account_name         = lower(substr(replace("stvey${var.app_name}${var.environment}${var.instance_seq}", "/[^a-z0-9]/", ""), 0, 24))
  log_analytics_workspace_name = "log-vey-${var.app_name}-${var.environment}-${var.instance_seq}"
  application_insights_name    = "appi-vey-${var.app_name}-${var.environment}-${var.instance_seq}"

  backend_api_name  = "app-vey-${var.app_name}-api-${var.environment}"
  frontend_spa_name = "app-vey-${var.app_name}-spa-${var.environment}"

  # Identifier URI for Entra ID backend API
  api_identifier_uri = "api://func-vey-${var.app_name}-${var.environment}"

  # Fallback to provider client tenant if entra_tenant_id is not specified
  tenant_id = var.entra_tenant_id != "" ? var.entra_tenant_id : data.azuread_client_config.current.tenant_id

  # Deduplicated list of allowed origins across local, configured origin, and optional portal subdomain
  # CORS origins MUST NOT have a trailing slash per RFC 6454
  cors_origins = distinct([
    for origin in compact(concat(
      [var.powerpages_origin],
      var.allowed_cors_origins,
      [var.powerpages_dev_subdomain != "" ? "https://${var.powerpages_dev_subdomain}.powerappsportals.com" : ""]
    )) : trimsuffix(origin, "/")
  ])

  # Portal routes where MSAL.js executes authentication
  spa_route_paths = [
    "",
    "/file-manager",
    "/file-manager/",
    "/submissions",
    "/submissions/"
  ]

  # Entra ID SPA redirect URIs require a trailing slash when there is no path segment (RFC 3986)
  spa_redirect_uris = distinct(flatten([
    for origin in local.cors_origins : [
      for path in local.spa_route_paths : (
        path == "" ? (
          can(regex("^https?://[^/]+$", origin)) ? "${origin}/" : origin
        ) : "${origin}${path}"
      )
    ]
  ]))

  common_tags = merge(
    var.tags,
    {
      Project     = "Veylo"
      Application = var.app_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  )
}
