packer {
  required_plugins {
    googlecompute = {
      source  = "github.com/hashicorp/googlecompute"
      version = "= 1.2.7"
    }
  }
}
variable "project_id" { type = string }
variable "zone" { type = string }
variable "subnetwork" { type = string }
variable "wheel" { type = string }
variable "workload_image" { type = string }
variable "image_name" { type = string }
source "googlecompute" "runner" {
  project_id                      = var.project_id
  zone                            = var.zone
  subnetwork                      = var.subnetwork
  source_image_family             = "debian-13"
  source_image_project_id         = ["debian-cloud"]
  image_name                      = var.image_name
  image_family                    = "agentbox-runner"
  machine_type                    = "e2-standard-2"
  disk_size                       = 30
  ssh_username                    = "packer"
  use_internal_ip                 = true
  omit_external_ip                = true
  use_iap                         = true
  use_os_login                    = true
  disable_default_service_account = true
  enable_secure_boot              = true
  tags                            = ["agentbox-runner"]
}
build {
  sources = ["source.googlecompute.runner"]
  provisioner "file" {
    source      = var.wheel
    destination = "/tmp/${basename(var.wheel)}"
  }
  provisioner "shell" {
    inline = ["mkdir -p /tmp/agentbox-files"]
  }
  provisioner "file" {
    source      = "../files/"
    destination = "/tmp/agentbox-files"
  }
  provisioner "shell" {
    script           = "provision.sh"
    environment_vars = ["AGENTBOX_WORKLOAD_IMAGE=${var.workload_image}", "AGENTBOX_WHEEL=/tmp/${basename(var.wheel)}"]
    execute_command  = "chmod +x {{ .Path }}; sudo -E env {{ .Vars }} {{ .Path }}"
  }
}
