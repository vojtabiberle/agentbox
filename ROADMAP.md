# Roadmap

Future development ideas for agentbox.

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
- [ ] Kubernetes, Terraform toolsets

## Toolsets

- [ ] `agentbox toolsets` command to list available toolsets with descriptions
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
- [ ] Other coding agents (Codex, etc.)

## Workspace Handling

- [x] Default to current directory if no workspace specified
- [x] Read-only directory mounts (`-r` or `--ro` flag) for providing context without write access
  ```bash
  agentbox run ~/worktrees/feature -r ~/repos/shared-libs -r ~/docs/api-specs
  ```

## Plugin System

- [ ] Toolsets as plugins — externalize toolset definitions:
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
  - **Image naming**: Create separate image `agentbox:<project-hash>` to avoid polluting base image
    - Allows per-project caching
    - Base `agentbox:latest` remains shared across projects
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
- [ ] Persistent package cache volume (npm, pip, etc.)
- [ ] Session naming for multiple concurrent containers
- [ ] `--name` flag for named sessions
