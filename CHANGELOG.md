# Changelog

## 0.2.1 — 2026-09-16

- Resolve `run` project configuration from the target workspace, including when
  the invoking directory has an invalid configuration.
- Reject cyclic toolset dependencies and handle repeated dependency names.
- Separate immutable run specifications and command rendering from execution.
- Validate required mount sources, deduplicate identical mounts and reject
  conflicting targets. Explicit Claude file/plugin paths must exist.
- Keep hostname and machine-id sharing specific to Claude.

## 0.2.0 — 2026-09-16

### Migration

Claude host configuration is no longer mounted automatically. Each workspace and
agent has a private persistent HOME at
`~/.local/state/agentbox/<workspace-path-hash>/<agent>/home`. Log in inside the
container, or explicitly set `claude.share_host_config: true` to reuse the former
read-write host configuration sharing. Existing host configuration is not deleted.
Moving a workspace changes its state identity. Back up private state before
removing it: it contains credentials, sessions, memory and user-installed tools.

Image tags now derive from generated Dockerfiles. `image_name` selects the image
repository; generated tags replace any configured tag.

### Added

- Hermes interactive CLI/setup with pinned source and locked dependencies.
- Agent-specific installation toolsets, mounts and forwarded CLI arguments.
- Writable persistent HOME/cache, isolated per workspace and agent (fixes #21).
- Minimal Kubernetes toolset: kubectl, helm and kustomize.
- `Dockerfile.agentbox` workspace extensions with injected base image, separate
  project tags and container-engine cache checks for COPY/ADD inputs.
- Container init process reaps child processes created by agents.
- Real-container regression tests for Podman and Docker; contributor instructions.

### Verification scope

Unit tests, type/lint checks, package installation, real container builds and
cache/state persistence are covered. Model calls require separately configured
provider access and are not part of default CI. Hermes gateway services remain
outside this release's scope.
