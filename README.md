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
agentbox run [OPTIONS] [WORKSPACE] [-- AGENT_ARGS...]

Arguments:
  WORKSPACE   Directory to mount read-write (default: current directory)

Options:
  --bash            Run bash instead of agent (for debugging)
  --agent, -a NAME  Agent to run (default: claude)
  --ro, -r PATH     Read-only directory to mount (repeatable)
  --rebuild         Force rebuild the container image

agentbox build [--agent NAME] [--rebuild]   Build the container image

agentbox config              Show current configuration
agentbox config show         Show current configuration (same as above)
agentbox config init         Create global config (~/.config/agentbox/config.yaml)
agentbox config init --project   Create project config (.agentbox.yaml in current dir)
agentbox config init --force     Overwrite existing config file

agentbox toolset <name>      Show details about a specific toolset

agentbox upgrade             Upgrade agentbox (if installed via install.sh)
```

### Agents and persistent HOME

```bash
# First-time Hermes setup, then interactive chat in the same workspace
agentbox run --agent hermes ~/workspace -- setup
agentbox run --agent hermes ~/workspace

# Forward options verbatim to the selected agent
agentbox run --agent hermes ~/workspace -- --help
agentbox build --agent hermes
```

Agent installation toolsets are included automatically. Hermes uses its local
terminal backend **inside** the agentbox container; no host container socket is
mounted. Hermes source is pinned in its toolset manifest and installed with its
upstream lockfile. Upgrade by changing the pin and rebuilding the image.

Every workspace/agent pair gets a writable HOME at
`~/.local/state/agentbox/<workspace-path-hash>/<agent>/home` on the host. Config,
cache, sessions, skills and memory persist across runs and image rebuilds. The
container HOME keeps the host home **path**, but its contents come from this private
directory. The host's actual home directories are not shared automatically.
Workspaces are identified by their resolved absolute path: moving a project starts
with new state. Different agents and worktrees have separate state and logins.
Concurrent runs of the same agent in the same workspace share that state.

Optional configuration:

```yaml
state_dir: ~/.local/state/agentbox
claude:
  share_host_config: false
```

**Migration:** Claude no longer automatically mounts host `~/.claude` and
`~/.claude.json`. Log in within the container, or explicitly set
`claude.share_host_config: true` to reuse the old behavior. That option exposes
those host files read-write and shares Claude state across workspaces. Explicit
`global_claude_md` and `plugins_dir` mounts remain read-only. Hermes starts with
fresh state; run its setup command instead of importing host secrets implicitly.

Cache/HOME writes work without the host-wide mounts proposed in PR #22. Existing
credential options and plugin mounts still opt into host sharing. Private state
contains secrets: back it up accordingly. To reset a workspace/agent, stop its
containers and delete only its corresponding state directory; this removes its
login, history and user-installed tools.

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
1. `.agentbox.yaml` or `.agentbox.yml` in the target workspace for `run`, otherwise the current directory (project config)
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

### Project-specific dependencies

Place `Dockerfile.agentbox` in the workspace root:

```dockerfile
RUN dnf install -y postgresql && dnf clean all
COPY requirements.txt /tmp/project-requirements.txt
```

Omit `FROM`: agentbox injects the selected agent/toolset image as the base.
`agentbox run <workspace>` and `agentbox build` (from the workspace directory)
then build a separate project image. Build context is the workspace; normal
`.dockerignore` rules apply. Only trusted project Dockerfiles should be built.

Changes to the base image or project instructions select a new project tag.
Each run asks the container engine to check the project build cache, so changes
to `COPY`/`ADD` inputs are picked up even when the Dockerfile itself is unchanged.
`--rebuild` invokes both base and project builds; normal engine layer caching still
applies. Nested monorepo directories are not searched automatically.

### Image Tagging

agentbox automatically tags container images based on your configuration:

- **Global config**: Uses a hash of the rendered Dockerfile (`agentbox:a1b2c3d4`)
- **Project config**: Uses unique tag based on project name and rendered Dockerfile hash (`agentbox:myproject-a1b2c3d4`)

Changing the selected agent or toolsets selects a different image when the generated
Dockerfile changes. Existing matching images are reused. `image_name` supplies the
repository name; any explicit tag is replaced by the generated tag.

## Toolsets

Toolsets are plugins that define what gets installed in your container image. Each toolset can include packages, configure mounts, and set environment variables.

### Built-in Toolsets

agentbox includes these built-in toolsets:

| Toolset | Description |
|---------|-------------|
| `base` | Git, Node.js, ripgrep, fd, bat, fzf, jq, yq, gh |
| `claude` | Claude Code CLI (automatically selected for Claude) |
| `hermes` | Hermes CLI, pinned source revision and locked Python dependencies |
| `python` | Python 3 + pip |
| `go` | Go programming language |
| `rust` | Rust via rustup |
| `php` | PHP + Composer |
| `cloud-aws` | AWS CLI (mounts `~/.aws`) |
| `cloud-azure` | Azure CLI (mounts `~/.azure`) |
| `cloud-gcloud` | Google Cloud CLI (mounts `~/.config/gcloud`) |
| `docker` | Docker CLI |
| `kubernetes` | Kubernetes CLI tools: kubectl, helm, kustomize |

Use `agentbox toolset <name>` to see details about a specific toolset, including mounts and dependencies.

### Kubernetes

Enable the minimal Kubernetes toolset in `.agentbox.yaml`:

```yaml
toolsets:
  - kubernetes
```

This installs `kubectl`, `helm`, and `kustomize` from Fedora packages; `base` and
the selected agent are included automatically. Configure cluster access in the
container's private HOME, or explicitly share selected files through a custom
plugin. Host `~/.kube` is not mounted automatically. Additional companion tools
and local cluster runtimes are outside this toolset's scope.

Build with `agentbox build`, then verify the printed image with the offline,
rootless Podman smoke test:

```bash
AGENTBOX_KUBERNETES_TEST_IMAGE=localhost/agentbox:<printed-tag> pytest -q tests/test_kubernetes.py
```

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
provides: [some-tool]  # Optional inventory; dependencies list their own tools

# Optional: Dockerfile fragment (RUN commands to install packages)
dockerfile: |
  RUN dnf install -y some-package && dnf clean all
  RUN pip install some-python-package

# Optional: directories to mount into container
mounts:
  - source: ~/.my-config        # Host path (~ expanded)
    target: /home/user/.my-config  # Container path
    readonly: true              # Optional, default: true
    required: false             # Optional, fail if source is missing when true
    relabel: true               # Optional, Podman SELinux relabeling
    description: My tool config # Optional, for documentation

# Optional: environment variables to set
environment:
  MY_VAR: some-value
  MY_CONFIG: /home/user/.my-config
```

Mounts with missing sources are skipped unless `required: true`. Explicit Claude
`global_claude_md` and `plugins_dir` paths are required. Identical mounts are
deduplicated; conflicting mounts at the same container path fail before startup.
Nested mounts remain supported, for example private HOME with a shared config
subdirectory. Host hostname and `/etc/machine-id` are shared only for Claude.

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

- **Workspace isolation**: The selected directory is mounted at `/workspace`; agentbox also mounts its private persistent HOME and explicitly configured mounts.
- **Agent state**: Private HOME per workspace and agent. Host Claude configuration is shared only with `claude.share_host_config: true`.
- **Rootless security**: Runs with `--userns=keep-id` and `--security-opt=no-new-privileges`
- **No network restrictions**: Full network access for package installation and API calls

## Limitations

- No access to host Docker/Podman socket (can't run containers inside)
- No GPU access
- Container is ephemeral — system package changes are lost between runs. Workspace files and private HOME (including user-local packages and cache) persist.
- Hermes integration currently targets interactive CLI/setup; gateway services are not managed.

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

### Real-container regression test

Build a Hermes image, then use the image name printed by the build:

```bash
agentbox build --agent hermes
AGENTBOX_TEST_IMAGE=localhost/agentbox:<printed-tag> pytest -q tests/test_runtime_integration.py
```

These tests default to rootless Podman and temporary state. Set
`AGENTBOX_TEST_RUNTIME=docker` to test Docker with an image loaded into that runtime.
They verify HOME/cache
writes, Hermes CLI/configuration startup, persistence after container restart,
and separation across agents and workspaces. They also download Corepack/Yarn and
check offline cache reuse after restart. They make no paid model calls.

To verify project Dockerfile builds and COPY cache invalidation:

```bash
AGENTBOX_PROJECT_TEST_RUNTIME=podman pytest -q tests/test_project_image.py
AGENTBOX_PROJECT_TEST_RUNTIME=docker pytest -q tests/test_project_image.py
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

### Rootless Docker

Agentbox detects the selected Docker daemon through `docker info` (including
`DOCKER_HOST` and Docker contexts). A standard daemon runs containers as the host
UID/GID. A rootless daemon runs them as container `0:0`, which maps to the
unprivileged daemon owner on the host and allows writes to bind-mounted HOME
and workspace directories. See [Docker UID mapping](https://docs.docker.com/engine/security/rootless/uid-gid-mapping/).

Verified with a separate rootless Docker 29.7.2 daemon: Hermes startup, private
HOME/cache persistence, Corepack/Yarn and project Dockerfile builds. This is
runtime verification; individual agents can impose their own container UID rules.
Run the opt-in runtime tests with `DOCKER_HOST` pointing to your rootless socket.

### Private state management

```bash
agentbox state show ~/project --agent hermes
agentbox state show ~/project --agent hermes --path-only
agentbox state list
agentbox state reset ~/project --agent hermes
```

`show` and `list` display paths and byte usage, never credentials or session text.
`reset` asks for confirmation (`--yes` confirms explicitly), refuses leased state
or state mounted by active containers, and deletes only the selected HOME. It
checks the current runtime and recorded endpoints from previous runs; an
unreachable endpoint causes refusal rather than assuming the state is unused.
The run lease coordinates startup/reset. Do not manually launch containers with
these state paths while resetting them.

For backup/restore, stop all containers using the selected state first. Backups
contain credentials; keep them private. The backup directory must not already
exist. Preserve permissions and symlinks:

```bash
state_path=$(agentbox state show ~/old-project --agent hermes --path-only)
umask 077
cp -a -- "$state_path" ~/private-agentbox-backup
```

A moved workspace gets a different state path. Restore into the new path while
its containers are stopped; reset an existing destination first if necessary:

```bash
new_state=$(agentbox state show ~/new-project --agent hermes --path-only)
mkdir -p -- "$(dirname "$new_state")"
# Destination HOME must not exist; otherwise cp would nest the backup.
test ! -e "$new_state" && cp -a -- ~/private-agentbox-backup "$new_state"
agentbox run --agent hermes ~/new-project
```

Restart once more and verify the expected session/config remains available.
