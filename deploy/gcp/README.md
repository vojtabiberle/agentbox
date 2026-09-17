# Private GCP runner (preview)

Implementation and local security tests are available. A DEV pilot on 2026-09-17
built and booted the image, verified IAP, container/host isolation, persistent stop
across reboot and a live Claude Haiku request through the broker. GitHub review
acceptance remains pending repository access for the DEV token (HTTP 404).
The 15-minute onboarding target remains an acceptance criterion, not a measured result;
the pilot used staged deployment with automatic workloads stopped.

The image is built once by maintainers. An end user selects the approved image and
supplies identifiers in a small JSON config, then runs:

```sh
./deploy/gcp/deploy ./runner.tfvars.json
```

The wrapper applies Terraform and waits for an actual container isolation probe.
It creates billable VM/disk/NAT resources. Run it only in the intended project.
`agentbox-ready` checks infrastructure/runtime readiness, not provider authorization
or a successful review. End-to-end acceptance is a separate step below.

## Prerequisites owned by the organization

- A billed DEV project with quotas and permission to enable Compute/IAP/Secret Manager
  APIs, create networking/VM/service accounts, and bind the required IAM roles.
- Administrators have IAP tunnel access, OS Admin Login and permission to use the
  runner service account. This module deliberately does not grant humans broad roles.
- Two **existing** Secret Manager secrets: Anthropic API key and either GitHub App
  RSA private key or a short-lived, fine-grained DEV personal token. Secret values
  never enter Terraform, instance metadata, image layers or the workload environment.
- GitHub App permissions: repository Contents read and Pull requests write, installed
  only on the intended repository. Set both App and installation IDs. In DEV PAT mode
  omit both IDs; scope the token to the same repository, give the minimum equivalent
  permissions and set an expiry. A PAT is not represented as a production App setup.
- An exact approved Anthropic model and reviewed **worst-case** request reservation.
  The sample 100 cents is illustrative and must be reviewed, not assumed adequate.

Populate secrets through the Secret Manager UI or a secure stdin workflow. Never put
values in tfvars, shell history, command arguments or chat. Creating secret resources
and accessing their versions are intentionally separate from Terraform deployment.

## Bake once

Use Packer 1.16+, Terraform 1.7+, gcloud and a locally built agentbox wheel containing
`agentbox server`. Packer uses the pinned googlecompute plugin and a private Debian 13
builder via IAP/OS Login, with **no VM service account**. The builder needs HTTPS NAT
and IAP firewall access. The Terraform module with `image = null` creates this
foundation and the per-runner IAM bindings; it does not start a workload VM.

```sh
python -m build
# Use a copy of the example with real identifiers and image=null for the first apply.
terraform -chdir=deploy/gcp/terraform init
terraform -chdir=deploy/gcp/terraform apply -var-file=/absolute/path/runner.tfvars.json
cd deploy/gcp/image
packer init .
packer build \
  -var project_id=YOUR-DEV-PROJECT \
  -var zone=europe-west1-b \
  -var subnetwork=SUBNETWORK-SELF-LINK-FROM-TERRAFORM \
  -var wheel=/absolute/path/to/agentbox-VERSION-py3-none-any.whl \
  -var workload_image=APPROVED-IMAGE-AT-SHA256-DIGEST \
  -var image_name=agentbox-runner-UNIQUE-VERSION .
```

Review/verify the workload image's provenance before baking. Use the published Python
stack for the example: the socket bridge requires Python 3 inside the image. Baking
preloads that exact digest into the dedicated rootless Podman store. At runtime,
`--pull=never` prevents both registry access and accidental substitution. Deploying a
different digest requires a new image bake; automatic OS updates do not update the
baked container or the agentbox package. Rebuild/replace VM images for those updates.

Set `image` in the JSON config to the resulting **versioned image self-link**, then
use the single deploy command. Keep one Terraform state per deployment; do not reuse
a state directory for unrelated users. For teams use a protected remote state backend.

## Boundaries

- No external VM IP; SSH only through IAP with OS Login, key authentication and no root login.
- Host APT security updates run automatically over HTTPS. Plan reboots for kernel
  updates; uninterrupted work across a reboot is not guaranteed.
- Dedicated non-login runner and broker users. Workload receives no capabilities,
  no-new-privileges, read-only root/workspace, bounded tmpfs HOME/tmp/run, no host
  credential mounts and no network interface except loopback.
- A root-owned nftables rule denies all IPv4/IPv6 egress for the runner UID, including
  the metadata endpoint. Podman additionally uses `network=none`. The broker's Unix
  socket is the only granted network capability; merely changing proxy variables
  cannot create a route out.
- Extra destinations are exact DNS names over CONNECT/443. Private/link-local/DNS
  rebinding targets are rejected. Empty allowlist suffices for the reference review.
- Workload socket supports the bounded Anthropic API, not GitHub credentials/actions.
  A separate unmounted controller socket can read PRs and create comments only in the
  configured repository. No merge, push, arbitrary repository or arbitrary API routes.
- Provider keys stay in broker memory; GitHub App signing uses an anonymous memory
  file. Swap and core dumps are disabled. Workload HOME is tmpfs and discarded.
- Secrets rotate via new Secret Manager versions; the next request reads `latest`.
  PAT expiry/revocation and App installation lifecycle remain provider responsibilities.

## Budget and model compatibility

The broker atomically reserves integer cents **before** every generation request.
Reservations are durable across restarts, never refunded, and reset by UTC day. The
input count endpoint gates input size; output tokens, exact model and request fields
are bounded. Paid provider-side tools, images, documents, remote input URLs, caching
and caller-supplied beta headers are disabled. Additional providers are not supported
by this budget path yet. HTTPS egress never carries the broker's provider credentials.

This is a conservative **admission budget**, not provider billing reconciliation.
A monetary upper bound depends on the administrator setting a valid worst-case
reservation for that exact model, input/output limits, token-count estimation and all
applicable pricing tiers. Configure a provider-side spending limit as a second brake.
An underestimated reservation or changed provider pricing invalidates the money-bound
claim; the software cannot promise a currency cap for unknown models/prices.

Responses (including SSE) are buffered up to 8 MiB, upstream socket reads time out at
30 seconds, and server runs time out after 600 seconds. This bounded preview may reject
long model calls. Live compatibility with the selected model must be verified in DEV.

## Review and acceptance

Copy `examples/scheduled-review/runner.example.tfvars.json`. The reference controller
polls every two minutes for directly requested reviews by the configured login (fewer
than 100 open PRs; team review requests are not included). It passes a bounded diff on
stdin to Claude Code with tools disabled, an empty read-only workspace and no cloned
repository. It rechecks the head SHA before posting a comment. It cannot approve,
merge or modify the repository. A durable `(repository, PR, SHA)` record prevents
repeat work. Failed/ambiguous runs stay recorded and require operator inspection before
retrying; this avoids duplicate comments after a crash around publication.

DEV acceptance, after credentials/project exist:

1. Deploy from the baked image, record elapsed time until `agentbox-ready` passes.
2. Request a review on a harmless test PR; verify one comment and no duplicate after
   the next poll or VM reboot. Test secret rotation and provider failures.
3. Use malicious diff instructions and attempts to alter `.agentbox.yaml`/Dockerfiles:
   they must remain data. Verify blocked direct IP, metadata, IPv6, unlisted domains,
   workspace/root writes, GitHub merge/other-repository routes and resource exhaustion.
4. Exhaust a small admission budget; verify the next generation never reaches the provider.
5. Invoke the kill switch during a run and reboot. No scheduled work should restart.

```sh
# Run through IAP as an OS administrator:
sudo agentbox-stop
sudo journalctl -u agentbox-review.service -u agentbox-broker.service
# Explicit restart after investigation:
sudo rm /etc/agentbox/STOP
sudo systemctl start agentbox-broker.service agentbox-review.timer
```

Lifecycle, destination decisions, budget reservations and GitHub actions are structured
journal events. Prompts, headers, token values and raw agent output are not journalled.
This is **not** a complete syscall/tool-command audit. Journals are protected from the
workload but not host administrators; connect your organization's journal collector
for off-host retention. Logging IAM is provided for a GCP collector; no collector is
installed automatically by this preview.

See [the threat model](../../docs/THREAT_MODEL.md) for exclusions. Destroy disposable
DEV infrastructure with Terraform when done; retained secrets are not destroyed.
