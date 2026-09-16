# Roadmap

Implementation plan accepted 2026-09-16.

## Current delivery: isolated home and multiple agents

1. [x] Implement the fix for #21: writable, persistent HOME owned by agentbox, isolated per
   workspace and agent. Do not mount host-wide cache/config/local directories.
   Supersedes the host-wide sharing approach in PR #22; explicit credential
   sharing remains available. Remote issue/PR status has not been changed.
2. [x] Separate Claude installation and mounts from the common runtime; resolve
   agent toolset dependencies before building; forward CLI arguments.
3. [x] Add Hermes interactive CLI and setup with a pinned installation and local
   terminal backend inside the container. Persist its config, sessions and memory.
4. [x] Verify HOME writes, restart persistence, project/agent isolation, and real
   Hermes startup. Run regression tests, lint and type checks.

Gateway/bot services and unattended operation remain a later, separate milestone.
Kubernetes toolset provides kubectl, helm and kustomize; companion tools remain deferred.

Validation: rootless Podman builds for Hermes and Claude; Hermes CLI/configuration
startup; Corepack/Yarn writes and offline cache reuse across container restarts;
project/agent state isolation. Authenticated model calls and Docker integration
have not been exercised. See README for the opt-in container tests.

## Container Runtime

- [x] Rootless Podman support (with `--userns=keep-id` and SELinux `:Z` labels)
- [x] Rootless Docker support (with `--user UID:GID`)

## Configuration

- [x] Config file support (`~/.config/agentbox/config.yaml`)
- [x] Configurable toolsets — select which dev tools to include:
  - Language runtimes: PHP, Go, Python, Node.js, Rust
  - Cloud CLIs: AWS, Azure, Google Cloud
  - Other tools: Docker CLI
- [ ] Pre-built image variants for common stacks (e.g., `agentbox:php`, `agentbox:python`)
- [x] Kubernetes toolset (kubectl, helm, kustomize)
- [ ] Terraform toolset

## Toolsets

- [x] `agentbox toolsets` command to list available toolsets with descriptions
- [ ] Toolset metadata — show what each toolset provides:
  - Installed packages/tools
  - Expected mount paths (e.g., `cloud-aws` expects `~/.aws`)
  - Environment variables set
- [ ] Configurable paths per toolset in config file (TBD):
  ```yaml
  toolsets:
    cloud-aws:
      enabled: true
      credentials_path: ~/.aws  # customizable
  ```

## Credential Sharing

- [x] Mount Azure CLI credentials (`~/.azure`)
- [x] Mount GitHub CLI credentials (`~/.config/gh`)
- [x] Mount AWS credentials (`~/.aws`)
- [x] Mount Google Cloud credentials (`~/.config/gcloud`)
- [x] SSH agent forwarding for git operations

## Claude Code Integration

- [x] Support for global CLAUDE.md (auto-mount into container)
- [x] Support for global skills/plugins directory
- [ ] Mount MCP server configurations

## Multiple Agents

- [x] Unified interface with `--agent` flag
- [ ] Aider agent implementation
- [x] Hermes interactive CLI
- [ ] Other coding agents (Codex, etc.)

## Workspace Handling

- [x] Default to current directory if no workspace specified
- [x] Read-only directory mounts (`-r` or `--ro` flag) for providing context without write access
  ```bash
  agentbox run ~/worktrees/feature -r ~/repos/shared-libs -r ~/docs/api-specs
  ```

## Plugin System

- [x] Toolsets as plugins — externalize toolset definitions:
  - Each plugin defines:
    - **Dockerfile fragment**: Commands to install tools/packages
    - **Runtime configuration**: Mounts, environment variables, etc.
  - Plugin manifest structure (e.g., `toolset.yaml`):
    ```yaml
    name: cloud-aws
    description: AWS CLI and SDK support

    dockerfile: |
      RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
          && unzip awscliv2.zip && ./aws/install && rm -rf aws awscliv2.zip

    mounts:
      - source: ~/.aws
        target: /home/user/.aws
        readonly: true
        description: AWS credentials and config

    environment:
      AWS_CONFIG_FILE: /home/user/.aws/config
    ```
  - Plugin discovery paths:
    - Built-in: `src/agentbox/plugins/`
    - User plugins: `~/.config/agentbox/plugins/`
    - Project plugins: `.agentbox/plugins/`
  - Benefits:
    - Users can create/share custom toolsets without forking
    - Cleaner separation of concerns (no giant Jinja2 template)
    - Easier to maintain and test individual toolsets

## Project-specific Customization

- [ ] `Dockerfile.agentbox` support — when found in project root, extend the base image:
  - Detects `Dockerfile.agentbox` in workspace root (monorepo subdirectories not supported for now)
  - Builds a project-specific image combining base toolsets + custom instructions
  - [x] **Image naming**: Create separate image `agentbox:<project>-<hash>` to avoid polluting base image
    - Allows per-project caching
    - Base `agentbox:latest` remains shared across projects (used for global config)
  - **Build rules**:
    - Custom file uses `FROM agentbox:latest` (injected automatically or required)
    - Runs after all toolset configuration is applied
    - Rebuilds when `Dockerfile.agentbox` changes (hash-based cache invalidation)
    - `--rebuild` flag forces rebuild of both base and project image
  - Example `Dockerfile.agentbox`:
    ```dockerfile
    # Additional project dependencies
    RUN apt-get update && apt-get install -y postgresql-client
    RUN pip install specific-package==1.2.3
    ```

## Quality of Life

- [x] `--rebuild` flag to force image rebuild
- [x] `--bash` flag to drop into bash instead of agent (for debugging)
- [x] Persistent package cache in private HOME (per workspace and agent)
- [ ] Session naming for multiple concurrent containers
- [ ] `--name` flag for named sessions
