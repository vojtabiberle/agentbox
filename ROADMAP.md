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
- [ ] SSH agent forwarding for git operations

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

## Quality of Life

- [x] `--rebuild` flag to force image rebuild
- [x] `--bash` flag to drop into bash instead of agent (for debugging)
- [ ] Persistent package cache volume (npm, pip, etc.)
- [ ] Session naming for multiple concurrent containers
- [ ] `--name` flag for named sessions
