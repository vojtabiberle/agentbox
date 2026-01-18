# agentbox

![License](https://img.shields.io/badge/license-BSL_1.1-blue)

Run AI coding agents in isolated containers with access only to your workspace.

## Why?

Claude Code with `--dangerously-skip-permissions` is powerful but risky on your main system. agentbox sandboxes the agent in a container where it can only access the workspace you specify — everything else on your system is isolated.

## Licensing

AgentBox is licensed under the [Business Source License 1.1](LICENSE) (BSL).

You are free to use this software for non-commercial purposes such as local development, personal automation, evaluation, and internal tooling.

Commercial usage (including SaaS offerings, resale, or monetized redistribution) requires a separate commercial license.

Starting from **2029-01-01** this project will automatically transition to **Apache License 2.0**.

For commercial licensing inquiries, contact the repository owner.

## Prerequisites

- [Podman](https://podman.io/) (recommended) or [Docker](https://www.docker.com/) for rootless containers
- Claude Code credentials at `~/.claude/.credentials.json` (run `claude` once to authenticate)

## Installation

### Recommended: pipx

```bash
pipx install agentbox
```

### Alternative: curl installer

```bash
curl -fsSL https://raw.githubusercontent.com/vojtabiberle/agentbox/main/install.sh | bash
```

This creates a self-contained installation at `~/.agentbox` and symlinks the binary to `~/.local/bin`.

To upgrade an install.sh installation:

```bash
agentbox upgrade
```

### From source

```bash
git clone https://github.com/vojtabiberle/agentbox.git
cd agentbox
pip install -e .
```

## Usage

```bash
agentbox run <workspace-directory>
```

### Examples

```bash
# Run Claude on current directory
agentbox run .

# Run Claude on a specific workspace
agentbox run ~/worktrees/myproject/feature-auth

# Debug the container (bash instead of Claude)
agentbox run ~/workspace --bash

# Mount read-only directories for context
agentbox run ~/workspace -r ~/docs/api-specs -r ~/shared-libs

# Force rebuild the container image
agentbox run ~/workspace --rebuild
```

### CLI Reference

```
agentbox run [OPTIONS] [WORKSPACE]

Arguments:
  WORKSPACE   Directory to mount read-write (default: current directory)

Options:
  --bash            Run bash instead of agent (for debugging)
  --agent, -a NAME  Agent to run (default: claude)
  --ro, -r PATH     Read-only directory to mount (repeatable)
  --rebuild         Force rebuild the container image

agentbox build [--rebuild]   Build the container image

agentbox config              Show current configuration
agentbox config show         Show current configuration (same as above)
agentbox config init         Create global config (~/.config/agentbox/config.yaml)
agentbox config init --project   Create project config (.agentbox.yaml in current dir)
agentbox config init --force     Overwrite existing config file

agentbox toolset <name>      Show details about a specific toolset

agentbox upgrade             Upgrade agentbox (if installed via install.sh)
```

### Recommended: Git Worktree Workflow

Git worktrees let you have multiple branches checked out simultaneously. Combined with agentbox, you can give Claude an isolated copy of your repo while keeping your main checkout untouched.

**Setup** (one-time):
```bash
mkdir -p ~/repos ~/worktrees
```

**Workflow**:
```bash
# Clone your repo as a bare repository
git clone --bare git@github.com:user/myproject.git ~/repos/myproject.git

# Create a worktree for Claude to work on
cd ~/repos/myproject.git
git worktree add ~/worktrees/myproject/feature-auth feature-auth

# Let Claude work on it in isolation
agentbox run ~/worktrees/myproject/feature-auth

# Review changes and clean up
cd ~/worktrees/myproject/feature-auth
git diff
git push origin feature-auth

# Remove the worktree when done
cd ~/repos/myproject.git
git worktree remove ~/worktrees/myproject/feature-auth
```

## Configuration

agentbox looks for configuration in this order:
1. `.agentbox.yaml` or `.agentbox.yml` in the current directory (project config)
2. `~/.config/agentbox/config.yaml` or `config.yml` (global config)
3. `~/.agentbox.yaml` (legacy global config)

Use `agentbox config init` to create a config file:

```bash
# Create global config
agentbox config init

# Create project-specific config
agentbox config init --project
```

### Global Config

Create `~/.config/agentbox/config.yaml`:

```yaml
# Container runtime: podman or docker
runtime: podman

# Toolsets to include in the container image
toolsets:
  - base      # git, Node.js, ripgrep, fd, bat, fzf, jq, yq, gh, Claude Code
  - python    # Python 3 + pip
  - go        # Go
  - rust      # Rust via rustup
  - php       # PHP + Composer
  - cloud-aws    # AWS CLI
  - cloud-azure  # Azure CLI
  - cloud-gcloud # Google Cloud CLI
  - docker       # Docker CLI

# Share credentials with the container (read-only)
credentials:
  github: true    # ~/.config/gh
  azure: true     # ~/.azure
  aws: false      # ~/.aws
  gcloud: false   # ~/.config/gcloud
  ssh_agent: true # Forward SSH agent (SSH_AUTH_SOCK)

# Claude-specific settings
claude:
  global_claude_md: ~/dotfiles/CLAUDE.md
  plugins_dir: ~/dotfiles/claude-plugins
```

### Project Config

Create `.agentbox.yaml` in your project directory to override global settings:

```yaml
# Project-specific toolsets
toolsets:
  - base
  - python
  - cloud-aws

# Project-specific credentials
credentials:
  aws: true
```

### Image Tagging

agentbox automatically tags container images based on your configuration:

- **Global config**: Uses default image name (`agentbox:latest`)
- **Project config**: Uses unique tag based on project name and config hash (`agentbox:myproject-a1b2c3d4`)

This allows multiple projects with different toolsets to coexist without rebuilding images.

## Toolsets

Toolsets are plugins that define what gets installed in your container image. Each toolset can include packages, configure mounts, and set environment variables.

### Built-in Toolsets

agentbox includes these built-in toolsets:

| Toolset | Description |
|---------|-------------|
| `base` | Git, Node.js, ripgrep, fd, bat, fzf, jq, yq, gh, Claude Code |
| `python` | Python 3 + pip |
| `go` | Go programming language |
| `rust` | Rust via rustup |
| `php` | PHP + Composer |
| `cloud-aws` | AWS CLI (mounts `~/.aws`) |
| `cloud-azure` | Azure CLI (mounts `~/.azure`) |
| `cloud-gcloud` | Google Cloud CLI (mounts `~/.config/gcloud`) |
| `docker` | Docker CLI |

Use `agentbox toolset <name>` to see details about a specific toolset, including mounts and dependencies.

### Toolset Discovery Paths

Toolsets are discovered from three locations (later overrides earlier):

1. **Built-in**: Packaged with agentbox (cannot be modified)
2. **User/Global**: `~/.config/agentbox/plugins/<toolset-name>/`
3. **Project**: `<workspace>/.agentbox/plugins/<toolset-name>/`

This means you can:
- Override built-in toolsets by creating one with the same name in user or project plugins
- Create custom toolsets for personal use (user plugins)
- Create project-specific toolsets (project plugins)

### Creating Custom Toolsets

To create a custom toolset, create a directory with a `toolset.yaml` file:

```
~/.config/agentbox/plugins/
└── my-toolset/
    └── toolset.yaml
```

Or for project-specific toolsets:

```
<workspace>/.agentbox/plugins/
└── my-toolset/
    └── toolset.yaml
```

### Toolset Structure

A `toolset.yaml` file has this structure:

```yaml
# Required fields
name: my-toolset
description: My custom development tools

# Optional: dependencies (will be loaded first)
depends_on:
  - base

# Optional: priority for ordering (lower = earlier, default: 50)
priority: 50

# Optional: Dockerfile fragment (RUN commands to install packages)
dockerfile: |
  RUN dnf install -y some-package && dnf clean all
  RUN pip install some-python-package

# Optional: directories to mount into container
mounts:
  - source: ~/.my-config        # Host path (~ expanded)
    target: /home/user/.my-config  # Container path
    readonly: true              # Optional, default: false
    description: My tool config # Optional, for documentation

# Optional: environment variables to set
environment:
  MY_VAR: some-value
  MY_CONFIG: /home/user/.my-config
```

### Example: Custom Node.js Toolset

```yaml
# ~/.config/agentbox/plugins/node-lts/toolset.yaml
name: node-lts
description: Node.js LTS with pnpm and common tools
depends_on:
  - base
priority: 55

dockerfile: |
  # Install pnpm globally
  RUN npm install -g pnpm

  # Install common dev tools
  RUN npm install -g typescript ts-node eslint prettier
```

### Example: Project-Specific Database Toolset

```yaml
# <workspace>/.agentbox/plugins/myproject-db/toolset.yaml
name: myproject-db
description: PostgreSQL client for myproject
depends_on:
  - base
priority: 90

dockerfile: |
  RUN dnf install -y postgresql && dnf clean all

environment:
  PGHOST: localhost
  PGPORT: "5432"
```

## How it works

- **Workspace isolation**: Only the specified directory is mounted at `/workspace`
- **Claude credentials**: `~/.claude` mounted read-write (shared with host)
- **Rootless security**: Runs with `--userns=keep-id` and `--security-opt=no-new-privileges`
- **No network restrictions**: Full network access for package installation and API calls

## Limitations

- No access to host Docker/Podman socket (can't run containers inside)
- No GPU access
- Container is ephemeral — installed packages are lost between runs (workspace files persist)

## Local Development

### Setup

```bash
git clone https://github.com/vojtabiberle/agentbox.git
cd agentbox

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Development Workflow

```bash
# Run CLI directly (after pip install -e .)
agentbox --help
agentbox run --help

# Test container builds correctly
agentbox build --rebuild

# Test with bash to inspect container environment
agentbox run /tmp/test-workspace --bash

# Test with different config (create .agentbox.yaml in current dir)
cat > .agentbox.yaml << 'EOF'
runtime: podman
toolsets:
  - base
  - python
EOF
agentbox build --rebuild
```

### Testing

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=agentbox

# Run specific test file
pytest tests/test_config.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Type checking
mypy src/agentbox

# Linting
ruff check src/agentbox

# Format code
ruff format src/agentbox
```

### Manual Testing Checklist

Before submitting changes, verify:

1. **Clean build**: `agentbox build --rebuild` completes without errors
2. **Bash mode**: `agentbox run /tmp/test --bash` drops into container shell
3. **Workspace mounting**: Files created in container appear on host
4. **Read-only mounts**: `agentbox run /tmp/test -r ~/some-dir` mounts correctly
5. **Config loading**: Custom `.agentbox.yaml` is respected
6. **Default workspace**: `agentbox run` uses current directory

### Project Structure

```
agentbox/
├── src/agentbox/       # Main package (src layout)
│   ├── cli.py          # Click CLI commands
│   ├── config.py       # Pydantic config + YAML loading
│   ├── container.py    # Podman/Docker abstraction
│   ├── image.py        # Dockerfile generation via Jinja2
│   ├── agents/         # Agent implementations
│   └── templates/      # Jinja2 Dockerfile templates
├── tests/              # pytest tests
├── pyproject.toml      # Package metadata + dependencies
└── install.sh          # curl installer script
```

## Trademark

AgentBox™ is a trademark of Vojta Biberle. Forks and derived works must use a different name and branding.
