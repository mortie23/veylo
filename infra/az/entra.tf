# -----------------------------------------------------------------------------
# 1. UUID Generator for OAuth2 Scope
# -----------------------------------------------------------------------------
resource "random_uuid" "file_upload_scope_id" {}

# -----------------------------------------------------------------------------
# 2. Backend API App Registration (Protected Function App API)
# -----------------------------------------------------------------------------
resource "azuread_application" "upload_api" {
  display_name    = local.backend_api_name
  identifier_uris = [local.api_identifier_uri]

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allows authenticated portal users to request upload tickets and download files."
      admin_consent_display_name = "Upload files to Veylo"
      enabled                    = true
      id                         = random_uuid.file_upload_scope_id.result
      type                       = "User"
      user_consent_description   = "Allows authenticated portal users to request upload tickets and download files."
      user_consent_display_name  = "Upload files to Veylo"
      value                      = "File.Upload"
    }
  }

  tags = ["Veylo", var.environment, "BackendAPI"]
}

resource "azuread_service_principal" "upload_api" {
  client_id                    = azuread_application.upload_api.client_id
  app_role_assignment_required = false
}

# -----------------------------------------------------------------------------
# 3. Frontend SPA App Registration (Power Pages Portal MSAL.js)
# -----------------------------------------------------------------------------
resource "azuread_application" "portal_spa" {
  display_name = local.frontend_spa_name

  single_page_application {
    redirect_uris = local.spa_redirect_uris
  }

  required_resource_access {
    resource_app_id = azuread_application.upload_api.client_id

    resource_access {
      id   = random_uuid.file_upload_scope_id.result
      type = "Scope"
    }
  }

  tags = ["Veylo", var.environment, "PowerPagesSPA"]
}

resource "azuread_service_principal" "portal_spa" {
  client_id                    = azuread_application.portal_spa.client_id
  app_role_assignment_required = false
}

# -----------------------------------------------------------------------------
# 4. Pre-Authorize Frontend SPA to Backend API (Suppresses user consent prompt)
# -----------------------------------------------------------------------------
resource "azuread_application_pre_authorized" "spa_to_api" {
  application_id       = azuread_application.upload_api.id
  authorized_client_id = azuread_application.portal_spa.client_id
  permission_ids       = [random_uuid.file_upload_scope_id.result]
}
