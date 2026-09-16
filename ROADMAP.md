# Roadmap

Updated 2026-09-16, after [PR #26](https://github.com/vojtabiberle/agentbox/pull/26).
All remaining items, including the former backlog, are now accepted implementation
scope. See [the delivery plan](docs/IMPLEMENTATION_PLAN.md) for functional slices,
acceptance checks and per-slice progress.

## Released: v0.2.0

Published [v0.2.0](https://github.com/vojtabiberle/agentbox/releases/tag/v0.2.0).
See [CHANGELOG.md](CHANGELOG.md) for migration details and [README.md](README.md)
for configuration, plugin examples and integration-test commands.

- [x] Private writable HOME and package caches, persistent per workspace and agent.
  Host-wide cache/config/local directories are not mounted implicitly.
- [x] Fix [issue #21](https://github.com/vojtabiberle/agentbox/issues/21), now closed.
  [PR #22](https://github.com/vojtabiberle/agentbox/pull/22) was closed as superseded
  by [PR #23](https://github.com/vojtabiberle/agentbox/pull/23).
- [x] Rootless Podman execution with UID mapping and SELinux mount labels.
- [x] Docker execution as the host UID/GID. Tested with a standard Docker daemon;
  this does not establish support for a rootless Docker daemon.
- [x] Claude and Hermes behind a common agent interface: `--agent`, required
  installation toolsets, explicit host mounts and CLI argument forwarding.
- [x] Pinned Hermes installation, local terminal backend and persistent
  configuration, sessions and memory.
- [x] Explicit Claude host-config sharing and read-only global CLAUDE.md/plugin
  mounts. These require configuration; host Claude files are not shared by default.
- [x] Project/global configuration and YAML toolset plugins discovered from
  `src/agentbox/plugins/builtin/`, `~/.config/agentbox/plugins/` and
  `<workspace>/.agentbox/plugins/`.
- [x] Language toolsets: PHP, Go, Python, Node.js and Rust. Cloud toolsets: AWS,
  Azure and Google Cloud. Docker CLI and minimal Kubernetes tools are available;
  Kubernetes includes kubectl, helm and kustomize.
- [x] `agentbox toolsets` lists plugins; `agentbox toolset NAME` shows dependencies,
  mounts, environment and Dockerfile instructions. A structured inventory of
  installed tools remains future work.
- [x] Optional GitHub/cloud credential mounts and SSH-agent forwarding.
- [x] Current-directory workspace default, additional read-only context mounts,
  Git worktree metadata mounts, `--bash` and `--rebuild`.
- [x] Workspace-root `Dockerfile.agentbox` extensions, content-tagged base images
  and separate project images. The container engine checks COPY/ADD inputs on
  each project build. Custom files omit `FROM` and use the Fedora base's tools
  (for example `dnf`, not `apt-get`).
- [x] Container init process, Python 3.10–3.13 CI and wheel/sdist installation checks.

### Verification completed

- Rootless Podman image builds for Claude and Hermes; Docker project builds.
- HOME writes, cache reuse after restart and workspace/agent state isolation on
  Podman and Docker. Corepack/Yarn also passed offline cache reuse after restart.
- Claude completed an authenticated model task and resumed in a new container.
- Hermes completed a model task using the requested `openai/gpt-5.6-sol`
  (provider `openai-api`, model `gpt-5.6-sol`) and recalled the task after restart.
  Provider access is required for these manual tests; model calls are not in CI.

## Released: v0.2.1

Merged in [PR #26](https://github.com/vojtabiberle/agentbox/pull/26), commit `ea7b4bd`.

- [x] Load `run` configuration from its target workspace, even when the invoking
  directory has invalid configuration.
- [x] Reject dependency cycles and handle repeated toolset dependency names.
- [x] Separate immutable `RunSpec` preparation, command rendering and execution.
  The runtime no longer receives configuration, agents or a mutable plugin manager.
- [x] Support noninteractive runs through the internal run specification.
  A public noninteractive CLI option is not implemented yet.
- [x] Validate required mount sources, deduplicate identical mounts and reject
  conflicting targets. Explicit Claude file/plugin paths must exist.
- [x] Make hostname and machine-id sharing specific to Claude.
- [x] Verify 318 tests passing in the default suite (6 optional integration tests
  skipped), 91% coverage, lint/type checks and CI on Python 3.10–3.13.
  The two real runtime tests also passed separately on both Podman and Docker.

## Next milestones — proposed priority

### 1. Release the completed fixes

- [x] Published [v0.2.1](https://github.com/vojtabiberle/agentbox/releases/tag/v0.2.1).

Done when: the release version and changelog agree, CI and distribution-install
checks pass for the release commit, and the tagged release includes wheel/sdist
artifacts plus notes about workspace configuration and required mount sources.

### 2. Verify rootless Docker explicitly

- [x] Rootless Docker 29.7.2 verified with Hermes/HOME/cache and project builds;
  automatic daemon detection selects the matching UID mapping.

Done when: workspace writes, private HOME ownership, restart persistence and
project image builds pass against that daemon. If UID mapping needs changes,
add regression coverage before marking support complete; otherwise document the
remaining limitation without claiming rootless Docker support.

### 3. Manage private agent state

- [x] Show each workspace/agent HOME location and disk usage without exposing
  credentials or session contents.
- [x] Document a backup/restore procedure, including moving a workspace, whose
  resolved path determines its state identity.
- [x] Provide an explicit reset for one workspace/agent, with confirmation and
  protection against deleting state used by a running container.

Done when: users can locate and back up their state, restore it into the intended
workspace/agent and verify persistence after restart. Reset must refuse active
state, require confirmation, and leave other agents, workspaces and host files
untouched. Tests must cover scope isolation and active-container refusal.

### 4. Complete toolset inspection

- [x] Show `required` and `relabel` mount settings in `agentbox toolset NAME`.
- [x] Add a small structured inventory of provided tools to manifests and display it.

Done when: built-in inventories match installation instructions, old/custom
manifests remain compatible, and CLI tests verify tools, mounts and environment.
Do not duplicate existing mount/environment metadata in a second configuration format.

## Backlog — scope and priority not committed

- Terraform toolset and additional Kubernetes companion tools, based on demand.
- Pre-built images for common stacks, with an agreed publishing/update policy.
- Per-toolset path overrides in project/global configuration; schema undecided.
- Explicit MCP configuration sharing.
- Additional agents such as Aider and Codex, each with installation, provider
  setup, isolation and restart verification.
- [x] Named concurrent containers through `--name`.
- [x] Public `--non-interactive` CLI operation with stdin/exit-code preservation
  and explicit `--env NAME` forwarding.
- Hermes gateway/bot services and unattended operation as a separate milestone,
  requiring a lifecycle, networking and credential design before implementation.
- Monorepo subdirectory customization beyond the workspace-root Dockerfile.
