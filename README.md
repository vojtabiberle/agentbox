# claude-danger

Run Claude Code in an isolated container (Podman or Docker) with access only to a specified workspace directory.

## Why?

Claude Code with `--dangerously-skip-permissions` is powerful but risky on your main system. This script sandboxes Claude in a container where it can only access the workspace you specify — everything else on your system is isolated.

## Prerequisites

- [Podman](https://podman.io/) (default) or [Docker](https://www.docker.com/) installed
- Claude Code credentials at `~/.claude/.credentials.json` (run `claude` once to authenticate)

## Installation

```bash
# Clone the repository
git clone https://github.com/vojtabiberle/agentbox.git

# Add to PATH (optional)
export PATH="$PATH:$(pwd)/agentbox/bin"
```

Or just copy `bin/claude-danger` anywhere in your PATH.

## Usage

```bash
claude-danger <workspace-directory>

# Use Docker instead of Podman
CONTAINER_ENGINE=docker claude-danger <workspace-directory>
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINER_ENGINE` | `podman` | Container runtime to use (`podman` or `docker`) |

### Examples

```bash
# Work on a feature branch in a dedicated worktree
claude-danger ~/worktrees/myproject/new-feature

# Create a fresh workspace for experiments
claude-danger ~/sandbox/experiment-1

# Work on an existing project
claude-danger ~/projects/my-app
```

### Recommended: Git Worktree Workflow

Git worktrees let you have multiple branches checked out simultaneously in separate directories. Combined with `claude-danger`, you can give Claude an isolated copy of your repo to work on while keeping your main checkout untouched.

**Setup** (one-time):
```bash
mkdir -p ~/repos ~/worktrees
```

**Workflow**:
```bash
# Clone your repo as a bare repository (or use existing clone)
git clone --bare git@github.com:user/myproject.git ~/repos/myproject.git

# Create a worktree for Claude to work on
cd ~/repos/myproject.git
git worktree add ~/worktrees/myproject/feature-auth feature-auth

# Let Claude work on it in isolation
claude-danger ~/worktrees/myproject/feature-auth

# When done, review changes and clean up
cd ~/worktrees/myproject/feature-auth
git diff  # review Claude's changes
git push origin feature-auth

# Remove the worktree when done
cd ~/repos/myproject.git
git worktree remove ~/worktrees/myproject/feature-auth
```

This approach keeps Claude isolated to a single worktree while you continue working in your main checkout.

The script will:
1. Create the directory if it doesn't exist (with confirmation)
2. Build the container image on first run (~5 minutes)
3. Launch Claude Code inside the container

## What's in the container

The container is based on Fedora 41 and includes:

| Category | Tools |
|----------|-------|
| Languages | Node.js, Python 3, Go, Rust, PHP |
| Cloud CLIs | AWS CLI, Azure CLI, Google Cloud CLI, GitHub CLI |
| Dev tools | git, ripgrep, fd, bat, fzf, jq, yq, vim, tmux |
| Package managers | npm, pip, composer, cargo |

## How it works

- **Workspace isolation**: Only the specified directory is mounted at `/workspace`
- **Persistent credentials**: Claude credentials are stored in a container volume (`claude-danger-config`) and reused across runs
- **Rootless security**: Runs with `--userns=keep-id` (Podman) or `-u $(id -u):$(id -g)` (Docker) and `--security-opt=no-new-privileges`
- **No network restrictions**: Container has full network access for package installation, API calls, etc.

## Limitations

- No access to host Docker/Podman socket (can't run containers inside)
- No SSH agent forwarding (yet)
- No GPU access
- Container is ephemeral — installed packages are lost between runs (workspace files persist)

## License

MIT
