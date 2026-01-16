# agentbox

Run AI coding agents in isolated containers with access only to your workspace.

## Why?

Claude Code with `--dangerously-skip-permissions` is powerful but risky on your main system. agentbox sandboxes the agent in a container where it can only access the workspace you specify — everything else on your system is isolated.

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
  github: true   # ~/.config/gh
  azure: true    # ~/.azure
  aws: false     # ~/.aws
  gcloud: false  # ~/.config/gcloud

# Claude-specific settings
claude:
  global_claude_md: ~/dotfiles/CLAUDE.md
  plugins_dir: ~/dotfiles/claude-plugins
```

## How it works

- **Workspace isolation**: Only the specified directory is mounted at `/workspace`
- **Persistent credentials**: Claude credentials stored in a named volume, reused across runs
- **Rootless security**: Runs with `--userns=keep-id` and `--security-opt=no-new-privileges`
- **No network restrictions**: Full network access for package installation and API calls

## Limitations

- No access to host Docker/Podman socket (can't run containers inside)
- No SSH agent forwarding (yet)
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

## License

MIT
