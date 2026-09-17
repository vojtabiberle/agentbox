# Roadmap

Updated 2026-09-17. The original roadmap, including the former backlog, was implemented in v0.3.0.
Operational hardening is delivered in v0.3.1 and v0.4.0. [The delivery plan](docs/IMPLEMENTATION_PLAN.md) records the twelve
functional slices and their acceptance checks. Release details and migration notes
are in [CHANGELOG.md](CHANGELOG.md); usage is in [README.md](README.md).

## Delivered in v0.3.0

- [x] Rootless Docker detection and UID mapping, alongside rootless Podman and
  standard Docker support.
- [x] Private workspace/agent state inspection, disk usage, scoped reset with
  active-container protection, and backup/restore/migration instructions.
- [x] Toolset inventories plus required/relabel mount inspection.
- [x] Named containers, noninteractive stdin and exit-code preservation, and
  explicit environment-variable forwarding.
- [x] Per-toolset mount source overrides and explicit read-only MCP config mounts.
- [x] Checksum-pinned Terraform and optional Kubernetes extras: kubectx, kubens, stern.
- [x] Codex and Aider adapters with pinned installations and private persistent HOME.
- [x] Workspace-confined monorepo Dockerfile selection with workspace-root context.
- [x] Managed Hermes gateway start/status/logs/stop, restart policy and private state.
- [x] GHCR base/Python/PHP images, scheduled/manual/release publishing, unique build
  tags and digest pinning; CLI/config image selection and explicit refresh.
- [x] Wheel/sdist release with checksums and clean installation verification.

## Previously delivered

### v0.2.1

- [x] Target-workspace configuration loading, dependency-cycle validation and
  repeated-dependency handling.
- [x] Immutable run preparation separated from container command execution.
- [x] Mount validation/deduplication and Claude-specific identity sharing.

### v0.2.0

- [x] Private persistent HOME/cache per workspace and agent; host-wide config/cache
  directories are not shared implicitly. Issue #21 resolved; PR #22 superseded by #23.
- [x] Claude and Hermes, common agent interface, local Hermes terminal backend,
  explicit Claude host configuration and read-only instruction/plugin mounts.
- [x] Project/global configuration and built-in/user/project YAML toolsets.
- [x] PHP, Go, Python, Node.js, Rust, AWS, Azure, Google Cloud, Docker CLI and minimal
  Kubernetes toolsets; optional credentials and SSH-agent forwarding.
- [x] Read-only context mounts, Git worktrees, shell mode, rebuilds, project
  Dockerfile extensions, container init, package installation and Python CI.

## Verification and operational scope

- 384 tests passed with all optional container integrations enabled; 90% coverage.
  Separate rootless Docker run: 27 runtime, state, service and image tests passed.
- Ruff, strict mypy, Python 3.10–3.13 CI and clean distribution installation checks.
- Claude and Hermes previously completed authenticated tasks and resumed across
  containers. Codex and Aider each completed a task and resumed with `gpt-5.6-sol`
  through OpenAI API. Model calls are manual, require provider access and are not CI.
- Published images are Linux amd64. ARM64 installer checksums exist for infrastructure
  tools; native ARM64 runtime validation and prebuilt publishing are not claimed.
- Gateway lifecycle/state safety is verified on Podman and rootless Docker. Live
  Telegram/Discord delivery requires user bot configuration and was not exercised.
- Rootless Docker verification used Hermes; individual agents can impose additional
  UID requirements. Agentbox does not bypass those restrictions automatically.
- GHCR base/Python/PHP publication and pull/start checks passed in
  [the publishing run](https://github.com/vojtabiberle/agentbox/actions/runs/35159137041).
  Anonymous registry access was verified for all three stacks.

## Operational hardening: v0.3.1 / v0.4.0

- [x] Supported Fedora base and patch release; rebuild/test published stacks.
- [x] `doctor` and side-effect-free `run --dry-run`, with redacted environment values.
- [x] Scheduled real Podman/Docker integration CI; no paid model calls.
- [x] Optional CPU/memory/PID limits and disabled networking.
- [x] Image inventory, vulnerability reports, build provenance and prebuilt tool checks.

See the delivery plan for acceptance criteria. Provider/bot configuration remains
an operational prerequisite.

### Hardening verification

- Fedora 44 builds/startup passed for Claude, Hermes, Codex and Aider; all three
  public stacks rebuilt successfully for v0.3.1.
- 416 tests passed with all optional local container tests enabled (90% coverage).
- Hosted Podman and Docker integration passed in
  [run 35192001117](https://github.com/vojtabiberle/agentbox/actions/runs/35192001117).
  Real memory/CPU/PID and offline networking checks also passed locally on both engines.
- Prebuilt executable probes reject missing commands without exposing arbitrary image
  output. Timed-out probes are removed; failed cleanup identifies the owned container.
- Image publication verifies every installed RPM name/version in both Syft and
  CycloneDX inventories. Grype scans Fedora data; findings remain report-only.
  Published provenance and SBOM attestations are verified against image digests.
- No additional paid model calls were made for these milestones.
