variable "environment" {
  description = "Target deployment environment (e.g., dev, ppd, prd)"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "australiaeast"
}

variable "app_name" {
  description = "Short application identifier for naming convention"
  type        = string
  default     = "portal"
}

variable "workload_unit" {
  description = "Workload unit identifier for the Function App (e.g., up for upload)"
  type        = string
  default     = "up"
}

variable "instance_seq" {
  description = "Instance sequence number formatted with leading zero"
  type        = string
  default     = "01"
}

variable "storage_account_tier" {
  description = "Performance tier for the Azure Storage Account"
  type        = string
  default     = "Standard"
}

variable "storage_account_replication_type" {
  description = "Replication type for Azure Storage Account (LRS, GRS, ZRS)"
  type        = string
  default     = "LRS"
}

variable "container_name" {
  description = "Private blob container name for file submissions"
  type        = string
  default     = "submissions"
}

variable "powerpages_origin" {
  description = "Primary Power Pages origin allowed in CORS (e.g., http://localhost:3000 or https://subdomain.powerappsportals.com)"
  type        = string
  default     = "http://localhost:3000"
}

variable "powerpages_dev_subdomain" {
  description = "Optional Power Pages dev portal subdomain (e.g., veylo-dev if using veylo-dev.powerappsportals.com)"
  type        = string
  default     = ""
}

variable "allowed_cors_origins" {
  description = "List of additional CORS origins for Function App and Storage Account"
  type        = list(string)
  default     = ["http://localhost:3000"]
}

variable "dataverse_url" {
  description = "Target Dataverse environment URL (e.g., https://org123.crm.dynamics.com)"
  type        = string
  default     = ""
}

variable "entra_tenant_id" {
  description = "Entra ID Tenant ID. If left empty, dynamically discovered from the current Azure CLI login context."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Custom resource tags to attach to all deployable Azure resources"
  type        = map(string)
  default     = {}
}
