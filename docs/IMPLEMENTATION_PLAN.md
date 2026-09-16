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
