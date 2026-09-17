mock_provider "google" {}
variables {
  project_id                = "example-dev-project"
  region                    = "europe-west1"
  zone                      = "europe-west1-b"
  image                     = "projects/example-dev-project/global/images/agentbox-test"
  workload_image            = "ghcr.io/vojtabiberle/agentbox@sha256:abdc11d0dff2d3a9525a8174b8ba056c25234df22dd1980cd286692692262570"
  github_secret_id          = "github-review-token"
  anthropic_secret_id       = "anthropic-key"
  repository                = "example/repo"
  reviewer                  = "example-user"
  model                     = "approved-model"
  request_reservation_cents = 100
}
run "private_runner" {
  command = plan
  assert {
    condition     = length(google_compute_instance.runner[0].network_interface[0].access_config) == 0
    error_message = "Runner must not get a public IP."
  }
  assert {
    condition     = google_compute_instance.runner[0].shielded_instance_config[0].enable_secure_boot
    error_message = "Secure Boot is required."
  }
  assert {
    condition     = google_compute_instance.runner[0].metadata["enable-oslogin"] == "TRUE"
    error_message = "OS Login is required."
  }
  assert {
    condition     = google_compute_firewall.iap.source_ranges == toset(["35.235.240.0/20"])
    error_message = "SSH must be restricted to IAP."
  }
  assert {
    condition     = google_compute_firewall.deny_egress.direction == "EGRESS" && one(google_compute_firewall.deny_egress.deny).protocol == "all"
    error_message = "Default egress deny is required."
  }
}
