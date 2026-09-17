variable "project_id" { type = string }
variable "region" { type = string }
variable "zone" { type = string }
variable "name" {
  type    = string
  default = "agentbox-runner"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,24}[a-z0-9]$", var.name))
    error_message = "Use a 6–26 character lowercase resource name."
  }
}
variable "image" {
  type        = string
  default     = null
  description = "Baked GCP image self-link; null creates only the image-build foundation."
}
variable "workload_image" {
  type = string
  validation {
    condition     = can(regex("^[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}$", var.workload_image))
    error_message = "Use an approved digest-pinned image with Python 3 and Claude Code."
  }
}
variable "github_secret_id" { type = string }
variable "anthropic_secret_id" { type = string }
variable "repository" { type = string }
variable "reviewer" { type = string }
variable "model" { type = string }
variable "github_app_id" {
  type    = number
  default = null
}
variable "github_installation_id" {
  type    = number
  default = null
}
variable "daily_budget_cents" {
  type    = number
  default = 500
  validation {
    condition     = var.daily_budget_cents > 0 && floor(var.daily_budget_cents) == var.daily_budget_cents
    error_message = "Budget must be positive integer cents."
  }
}
variable "request_reservation_cents" {
  type        = number
  description = "Reviewed upper-bound charge per request for the selected model/input/output limits, including pricing tiers. Never a typical/average request cost."
  validation {
    condition     = var.request_reservation_cents > 0 && floor(var.request_reservation_cents) == var.request_reservation_cents
    error_message = "Reservation must be positive integer cents."
  }
}
variable "allowed_hosts" {
  type        = list(string)
  default     = []
  description = "Extra HTTPS destinations; empty suffices for the reference review. API credentials use broker routes only."
}
