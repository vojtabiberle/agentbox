# Roadmap delivery plan

Accepted scope: all remaining ROADMAP.md items, including the former backlog.
Each numbered slice receives implementation, regression checks, a commit and PR,
then merges only after CI passes. External validation is recorded separately from
implemented support. No model credentials are stored in the repository.

| Slice | Implementation plan | Acceptance | Status |
| --- | --- | --- | --- |
| 1. Patch release | Version 0.2.1; migration notes; wheel and sdist; GitHub release. | Release assets install and tagged CI passes. | Done: PR #28, v0.2.1 |
| 2. Rootless Docker | Detect rootless daemon; use correct UID mapping; test HOME and project builds. | Real rootless daemon smoke, or precise documented host prerequisite if unavailable. | Done: PR #29; 11 real rootless/runtime/project tests |
| 3. Private state | Shared state paths; location/size CLI; safe scoped reset; backup/restore guide. | Isolation, symlink safety, active-container refusal and restart tests. | Done: PR #30; state CLI, leases, endpoint checks and tests |
| 4. Toolset inspection | Optional provided-tools inventory; show required/relabel metadata. | Existing manifests compatible, inventories match installers, CLI tests. | Done: PR #31; optional provides field and CLI metadata |
| 5. Runtime controls | Named sessions, noninteractive CLI, explicit environment forwarding. | stdin and exit status preserved; no TTY in batch mode; validated names. | Done: PR #32; batch/name/env controls with real runtime tests |
| 6. Mount configuration | Typed per-toolset source overrides and explicit MCP config mounts. | Unknown overrides rejected; paths scoped consistently; no implicit secrets. | Done: PR #33; typed source overrides and MCP mounts |
| 7. Additional toolsets | Terraform plus optional Kubernetes companion tools. | Reproducible installers and actual command startup checks. | Done: PR #34; pinned installers; four executable smokes passed on amd64 |
| 8. Agents | Codex and Aider adapters/toolsets with provider setup documentation. | Isolated HOME, install/start/restart smoke; model tests where credentials permit. | Done: PR #35; startup/isolation and authenticated task/resume verified for both agents |
| 9. Monorepos | Explicit project Dockerfile selection inside workspace. | Path confinement; build context/cache tests; default unchanged. | Done: PR #36; explicit selection with confinement/cache tests |
| 10. Gateway services | Opt-in Hermes gateway lifecycle, named detached containers, logs/stop/status; minimal network exposure. | Lifecycle tests, private state, documented provider/bot credential setup. | Done: PR #37; lifecycle and active-state checks on Podman/rootless Docker |
| 11. Prebuilt images | CI builds/publishes a small stack matrix to GHCR; versioned tags and update policy. | Registry artifacts published and pulled for smoke testing. | Done: PR #38; all three GHCR variants published/pulled/started; anonymous access verified |
| 12. Final release | Reconcile roadmap/changelog with delivered features and actual verification; publish release. | Full CI, runtime and package checks; no unchecked implementation items. | Done in v0.3.0: 384 tests, 27 rootless checks, wheel/sdist; release artifacts published after green CI |

State reset must never remove another agent/workspace or follow a host symlink.
Gateway operation uses an explicit service command, not an implicit background run.
Bot credentials and external provider availability may require user setup; do not
claim end-to-end provider validation when only offline lifecycle tests ran.

## Operational hardening (accepted 2026-09-17)

Each slice receives tests, a PR and a merge after green CI. No new paid model calls.

| Slice | Plan | Acceptance | Status |
| --- | --- | --- | --- |
| 13. Supported base | Move to Fedora 44; patch release 0.3.1; rebuild public stacks. | Real base/agent startup and published stack tests; package CI. | Done: PR #40, v0.3.1; four agents built/started, 10 real checks |
| 14. Diagnostics | Doctor checks runtime/workspace/mounts/image; dry-run renders redacted resolved specification without builds, pulls or state creation. | No mutation and no secret values in output; actionable failures. | Done: PR #41; redacted preview and doctor; real Podman checks passed |
| 15. Integration CI | Scheduled/manual Podman and Docker builds with real persistence/reset/project/service tests. | Both runtime jobs pass without model credentials. | Done: PR #42; hosted Podman/Docker run 35191240839 passed |
| 16. Resource controls | Validated memory/CPU/PID/network settings in config and CLI, shared by services. | Render tests and real runtime inspection/offline execution. | Done: PR #43; CPU/memory/PID cgroups and offline network verified on Podman/Docker |
| 17. Image trust | Tool inventory and versions; vulnerability report; provenance attestation; check required executables before using prebuilt images. | Published reports/attestation, missing-tool rejection and successful compatible image run. | Done: PR #44/#45; Syft/Grype completeness/feed gates and signed image evidence |

Final release: v0.4.0, 419 passing tests (90% coverage), hosted Podman/Docker verification,
clean package installation and published image reports/attestations.

## Dependency remediation (accepted 2026-09-17)

1. Assess all v0.4.0 base/Python/PHP findings against advisory conditions and exact artifact paths.
2. Replace lagging distribution Go binaries and package-manager bundles with checksum-pinned upstream releases; preserve tool availability.
3. Build and scan all three stacks; exercise Git LFS, gh, yq, npm and pip. Record remaining matches with evidence, without suppressing raw reports.
4. Run Python CI and real runtime checks; commit, PR and merge after verification, then publish patched images/release.

Acceptance: no Critical findings in the three rebuilt images; any remaining findings explicitly assessed with version-scoped evidence. No paid model calls.

Delivered in v0.4.1: all three local scans report 0 Critical / 3 High / 0 Medium /
0 Low / 2 Unknown findings. The five residual Go module matches have exact-version
source dependency evidence in [the assessment](SECURITY_ASSESSMENT.md).
420 local tests passed (90% coverage); offline tool operations and Claude startup
passed on all three rebuilt stacks. PR #46 contains the fixes and CI verification.

## Always-on runner delivery

1. **Server policy and batch runner**: add a separate `agentbox server` entry point that never loads workspace configuration. Root-owned policy fixes the image digest, workspace root, command, limits and optional broker socket. Only rootless Podman is supported. Drop capabilities, use a read-only root, temporary HOME/tmp, no host credentials or network. Timeout/termination removes the owned container; bounded output and lifecycle events omit secrets.
2. **Broker boundary**: Unix socket is the only network capability. Exact-host HTTPS allowlist rejects private/link-local addresses and direct-IP targets; model calls pass through a separate budget/credential path. Secrets stay in broker memory. Kill file is checked by runner and broker. Test bypasses and fail-closed behavior.
3. **Deployment**: bake a private GCP VM image; Terraform supplies IAM, private networking, IAP, Secret Manager access and configuration without secret payloads. Dedicated system users separate supervisor, workload and broker. Systemd boots services and timers; host security updates are automatic. Validate Terraform/Packer and units; only deploy to an explicitly selected project.
4. **Reference workload**: trusted controller polls GitHub using an installation token, snapshots PR data without executing repository code, invokes Claude Code in the server profile, and publishes one review per head SHA. Keep the GitHub App signing key outside the workload. Test deduplication and adversarial inputs without posting externally.
5. **Acceptance/release**: real local container negative tests (network, metadata, mounts, policy, root, timeout/kill), mocked broker/provider/controller tests, hosted runtime CI, threat model, reproducible deploy instructions. Each functional slice gets a tested PR/merge. Report cloud/provider verification separately; no new paid model calls without authorization.

Local execution milestone: administrator policy, Unix broker and reference controller
implemented together because their capability boundary is tested end-to-end. 32 boundary
tests passed, including real Podman network/filesystem/UID checks, timeout/output cleanup
and the actual container-to-Unix bridge. GitHub signing/provider calls use test doubles;
no external comments or paid requests were sent. Deployment is a separate PR.

Deployment milestone: Packer recipe and private-VM Terraform module implemented;
Terraform validate plus mocked network/VM assertions and Packer validate pass.
The single deployment wrapper includes readiness checks; systemd units, persistent
kill switch, host UID egress denial, Secret Manager IAM and DEV PAT/App modes are
documented. Real Claude Code completed an offline review against a local mocked
Anthropic endpoint, exercising its actual request shape and SSE response.
Final local verification: 453 tests passed with all optional container suites enabled
(85% coverage); 33 server tests also pass with resource warnings treated as errors.
Wheel and source distribution build successfully; Terraform caches/state are excluded.

DEV pilot (2026-09-17): user-authorized GCP project and Secret Manager credentials
were provisioned. The first image build exposed an inherited inaccessible SSH working
directory when switching to the runner user; provisioning/readiness/stop scripts now
change to an accessible directory first. The corrected image built in 6m29s and booted
as a new private VM. IAP, host UID network denial (including metadata), container
isolation, SSH settings, upgrade timers and persistent stop across reboot passed.
A live synthetic Claude Haiku request through the broker completed in 5.3s. No
external GitHub comments were created. GitHub review acceptance currently stops at
HTTP 404 with the DEV token; repository access, rotation and timed one-command
onboarding remain open. Pilot VMs used two-hour maximum runtimes and staged startup.
