terraform {
  required_version = ">= 1.7.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}
provider "google" {
  project = var.project_id
  region  = var.region
}
resource "google_project_service" "apis" {
  for_each           = toset(["compute.googleapis.com", "iam.googleapis.com", "iap.googleapis.com", "secretmanager.googleapis.com", "logging.googleapis.com"])
  service            = each.key
  disable_on_destroy = false
}
resource "google_compute_network" "runner" {
  name                    = var.name
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}
resource "google_compute_subnetwork" "runner" {
  name                     = var.name
  network                  = google_compute_network.runner.id
  ip_cidr_range            = "10.77.0.0/24"
  private_ip_google_access = true
}
resource "google_compute_router" "runner" {
  name    = var.name
  network = google_compute_network.runner.id
}
resource "google_compute_router_nat" "runner" {
  name                               = var.name
  router                             = google_compute_router.runner.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"
  subnetwork {
    name                    = google_compute_subnetwork.runner.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}
resource "google_compute_firewall" "iap" {
  name          = "${var.name}-iap-ssh"
  network       = google_compute_network.runner.name
  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["agentbox-runner"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
resource "google_compute_firewall" "deny_egress" {
  name               = "${var.name}-deny-egress"
  network            = google_compute_network.runner.name
  direction          = "EGRESS"
  priority           = 2000
  destination_ranges = ["0.0.0.0/0"]
  deny { protocol = "all" }
}
resource "google_compute_firewall" "host_https" {
  name               = "${var.name}-host-https"
  network            = google_compute_network.runner.name
  direction          = "EGRESS"
  priority           = 1000
  target_tags        = ["agentbox-runner"]
  destination_ranges = ["0.0.0.0/0"]
  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}
resource "google_service_account" "runner" {
  account_id   = var.name
  display_name = "Agentbox broker (no project-wide secret access)"
  depends_on   = [google_project_service.apis]
}
resource "google_secret_manager_secret_iam_member" "secrets" {
  for_each   = toset([var.github_secret_id, var.anthropic_secret_id])
  secret_id  = each.key
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.runner.email}"
  depends_on = [google_project_service.apis]
}
resource "google_project_iam_member" "logging" {
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runner.email}"
  project = var.project_id
}
resource "google_compute_instance" "runner" {
  count        = var.image == null ? 0 : 1
  name         = var.name
  machine_type = "e2-standard-2"
  zone         = var.zone
  tags         = ["agentbox-runner"]
  boot_disk {
    initialize_params {
      image = var.image
      size  = 30
      type  = "pd-balanced"
    }
  }
  network_interface { subnetwork = google_compute_subnetwork.runner.id }
  service_account {
    email  = google_service_account.runner.email
    scopes = ["cloud-platform"]
  }
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }
  metadata = {
    enable-oslogin           = "TRUE"
    block-project-ssh-keys   = "TRUE"
    disable-legacy-endpoints = "TRUE"
    serial-port-enable       = "FALSE"
  }
  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    server = base64encode(yamlencode({
      image           = var.workload_image
      workspace_root  = "/var/lib/agentbox-runner/workspaces"
      command         = ["claude", "--print", "--output-format", "text", "--model", var.model, "--max-turns", "3", "--tools", "", "--disable-slash-commands"]
      broker_socket   = "/run/agentbox-broker/proxy.sock"
      memory          = "2g"
      cpus            = 1
      pids            = 256
      timeout_seconds = 600
      output_bytes    = 262144
    }))
    broker = base64encode(yamlencode({
      anthropic_secret          = "projects/${var.project_id}/secrets/${var.anthropic_secret_id}/versions/latest"
      github_secret             = "projects/${var.project_id}/secrets/${var.github_secret_id}/versions/latest"
      github_repository         = var.repository
      github_app_id             = var.github_app_id
      github_installation_id    = var.github_installation_id
      model                     = var.model
      daily_budget_cents        = var.daily_budget_cents
      request_reservation_cents = var.request_reservation_cents
      allowed_hosts             = var.allowed_hosts
    }))
    review = base64encode(yamlencode({ repository = var.repository, reviewer = var.reviewer }))
  })
  depends_on = [google_compute_router_nat.runner, google_secret_manager_secret_iam_member.secrets]
}
output "subnetwork" { value = google_compute_subnetwork.runner.self_link }
output "instance" { value = try(google_compute_instance.runner[0].name, null) }
