# agentbox

![License](https://img.shields.io/badge/license-BSL_1.1-blue)

Run Claude Code, Hermes, Codex and Aider in containers with an explicit workspace,
private agent state and optional mounts. An administrator-controlled server preview
adds a networkless runner, credential broker and private GCP deployment.

## Why?

Claude Code with `--dangerously-skip-permissions` is powerful but risky on your main system.
agentbox limits filesystem access to the workspace, private agent HOME and explicitly
configured mounts. Local runs have network access by default; the server profile uses
a separate, stricter policy. Containers share the host kernel; see the
[threat model](docs/THREAT_MODEL.md) for server trust boundaries and exclusions.

## Current capabilities and hackathon fit

Status: 2026-09-17. This checkout is **0.5.0a1**, including the always-on server
preview. Use the [source installation](#from-source) for that preview; do not assume
the latest stable package or published workload image includes the server changes.
See [release history](CHANGELOG.md) and [delivered work / remaining acceptance](ROADMAP.md).

| Area | Available now | Guide |
| --- | --- | --- |
| Coding agents | Claude Code, Hermes, Codex, Aider; private persistent HOME per workspace/agent | [Agents](#agents-and-persistent-home), [Codex/Aider](#codex-and-aider) |
| Development environments | Language/cloud toolsets, Kubernetes/Terraform, project Dockerfiles, worktrees, read-only context and MCP config mounts | [Toolsets](#toolsets), [project dependencies](#project-specific-dependencies), [MCP](#toolset-paths-and-mcp-configuration) |
| Automation | Noninteractive stdin/exit status, named containers, explicit environment forwarding, managed Hermes gateway | [Batch runs](#batch-runs-and-container-names), [services](#hermes-gateway-service) |
| Operations | State inspection/reset, doctor, dry-run access plan, CPU/memory/PID/network controls | [State](#private-state-management), [diagnostics](#diagnostics-and-preview), [limits](#resource-and-network-controls) |
| Images | Published amd64 base/Python/PHP stacks, digest pinning, compatibility probes, SBOM, vulnerability gate and attestations | [Images](#prebuilt-images), [publication evidence](#image-compatibility-and-publication-evidence) |
| Always-on preview | Administrator policy, rootless Podman, temporary HOME, broker-held secrets, bounded Anthropic requests, review controller, kill switch | [Server](#always-on-server-preview) |
| GCP preview | Packer image and Terraform wrapper, private VM, IAP/OS Login, automatic OS updates, dedicated identities and systemd supervision | [Deployment and acceptance](deploy/gcp/README.md) |

### Choose the execution profile

| Boundary | Local `run` / Hermes `service` | `server` preview |
| --- | --- | --- |
| Configuration | Workspace/user config, toolsets and trusted project builds | Root-owned policy; ignores project config/plugins/Dockerfiles |
| Runtime | Podman or Docker | Rootless Podman only; non-root workload UID |
| State | Persistent private HOME; workspace writable | Temporary HOME; workspace read-only by default, writable only by administrator policy |
| Network | Engine default, or explicitly `none` | No direct IP network; optional Unix broker |
| Credentials | Explicit mounts, agent login or forwarded environment; HOME can contain secrets | Broker reads Secret Manager; provider/GitHub credentials stay outside workload |
| Images | Local builds or selected prebuilt image | Preloaded digest-pinned image; no runtime pull/build |

**Always-on runner hackathon:** the infrastructure and reference scheduled-review
implementation are available. The GCP DEV pilot verified isolation, IAP, persistent
stop across reboot and a live one-shot GitHub diff review through Anthropic. It did
not publish a comment. Secret rotation, scheduled trigger/publication and measured
onboarding within 15 minutes remain acceptance work. The deployment command requires
an approved baked image, project/IAM and existing secrets; it creates billable resources.

**Fabro / Connection factory hackathon:** reuse the GCP/security foundation and
development images. There is **no Fabro integration or validated Connection builder**
yet. The Docker toolset installs a CLI; agentbox does not expose a host Docker socket
or provide a nested Docker/Compose environment. Connection build/Compose/`./bin/kbc`
and E2E execution have not been validated here. Workflow orchestration, approval gates,
multi-model review, Actions dispatch/result/cancel integration, exact-candidate evidence
and independent hidden E2E tests must still be implemented. The current broker supports
bounded Anthropic calls and restricted PR/comment routes, not a general multi-provider
gateway or GitHub builder API. A future integration should keep Fabro's orchestration,
builder execution and hidden verification in separate trust boundaries.

## Licensing

AgentBox is licensed under the [Business Source License 1.1](LICENSE) (BSL).

You are free to use this software for non-commercial purposes such as local development, personal automation, evaluation, and internal tooling.

Commercial usage (including SaaS offerings, resale, or monetized redistribution) requires a separate commercial license.

Starting from **2029-01-01** this project will automatically transition to **Apache License 2.0**.

For commercial licensing inquiries, contact the repository owner.

## Prerequisites

- [Podman](https://podman.io/) (recommended) or [Docker](https://www.docker.com/) for rootless containers
- Provider access for the selected agent; configure it inside its private HOME or
  forward credentials explicitly. Host Claude credentials are not shared by default.
- Server/GCP prerequisites differ; follow the [deployment guide](deploy/gcp/README.md).

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
  --image REF       Select a prebuilt image
  --dockerfile PATH Select a project Dockerfile inside the workspace
  --no-git-mount    Disable automatic Git worktree mounting
  --non-interactive Forward stdin without a TTY
  --env NAME        Forward an existing host variable (repeatable)
  --name NAME       Set a unique container name
  --memory SIZE     Set container memory limit
  --cpus NUMBER     Set CPU quota
  --pids-limit N    Set process limit
  --network MODE    Use default or none
  --dry-run         Print a redacted access plan without starting a container

agentbox build [--agent NAME] [--image REF] [--dockerfile PATH] [--rebuild]

agentbox config              Show current configuration
agentbox config show         Show current configuration (same as above)
agentbox config init         Create global config (~/.config/agentbox/config.yaml)
agentbox config init --project   Create project config (.agentbox.yaml in current dir)
agentbox config init --force     Overwrite existing config file

agentbox toolset <name>      Show details about a specific toolset
agentbox toolsets            List available toolsets
agentbox doctor WORKSPACE [--agent NAME]   Check local runtime/configuration
agentbox state show|list|reset            Inspect or reset private agent HOME
agentbox service start|status|logs|stop    Manage Hermes gateway containers
agentbox server run WORKSPACE             Run an administrator-approved workload
agentbox server broker                   Serve the credential/egress broker
agentbox server review-once              Poll assigned PRs for reference review

agentbox upgrade             Upgrade agentbox (if installed via install.sh)
```

Use `agentbox COMMAND --help` for command-specific arguments and defaults.

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
| `codex` | Codex CLI (automatically selected for Codex) |
| `aider` | Aider CLI (automatically selected for Aider) |
| `python` | Python 3 + pip |
| `go` | Go programming language |
| `rust` | Rust via rustup |
| `php` | PHP + Composer |
| `cloud-aws` | AWS CLI (mounts `~/.aws`) |
| `cloud-azure` | Azure CLI (mounts `~/.azure`) |
| `cloud-gcloud` | Google Cloud CLI (mounts `~/.config/gcloud`) |
| `docker` | Docker CLI |
| `kubernetes` | Kubernetes CLI tools: kubectl, helm, kustomize |
| `kubernetes-extras` | kubectx, kubens and stern; includes `kubernetes` |
| `terraform` | Checksum-pinned Terraform CLI |
| `ghostty` | Ghostty terminal information |

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

For local `run` and `service` (the [server profile](#always-on-server-preview) differs):

- **Workspace isolation**: The selected directory is mounted at `/workspace`; agentbox also mounts its private persistent HOME and explicitly configured mounts.
- **Agent state**: Private HOME per workspace and agent. Host Claude configuration is shared only with `claude.share_host_config: true`.
- **User mapping**: Podman uses `--userns=keep-id`; Docker uses runtime-specific UID mapping. Both use `--security-opt=no-new-privileges`.
- **Network**: Normal engine networking by default; `--network none` disables external access.

## Limitations

- No access to host Docker/Podman socket (can't run containers inside)
- No GPU access
- Container is ephemeral — system package changes are lost between runs. Workspace files and private HOME (including user-local packages and cache) persist.
- Hermes gateway services require explicit provider/platform configuration; agentbox manages their container lifecycle.

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

## Runtime and operations guide

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

### Batch runs and container names

```bash
printf 'input\n' | agentbox run --bash --non-interactive --name example ~/project -- -c 'read line; echo "$line"'
agentbox run --agent hermes --non-interactive --env OPENAI_API_KEY ~/project -- chat --provider openai-api --model gpt-5.6-sol --query 'Summarize this project'
```

`--non-interactive` forwards stdin without a TTY. The container/agent exit status
is the CLI exit status; stdout/stderr remain attached. Agentbox does not attempt
interactive provider login in batch mode: configure provider access beforehand.
`--env NAME` forwards only an explicitly named existing environment variable;
its value is not embedded in container command arguments. The container runtime
can still inspect its environment. Named containers must have unique names;
agentbox never replaces an existing container. Names do not change the per-agent,
per-workspace state identity. Completed foreground containers are removed.

### Toolset paths and MCP configuration

Override sources by toolset name and the target declared in its manifest. Targets
and access policies remain unchanged. Explicit override sources must exist;
relative paths resolve from the target workspace. Unknown toolsets/targets fail.

```yaml
toolsets: [base, cloud-aws]
toolset_mounts:
  cloud-aws:
    /home/user/.aws: ./private/aws
mcp_mounts:
  - source: ./private/mcp.json
    target: /workspace/.mcp.json
```

MCP mounts are opt-in, read-only and required by default. Use the configuration
format and destination supported by the selected agent (the example supplies a
project `.mcp.json`). Agentbox shares the file; it does not start host MCP servers
or make host executables available inside the container. Server commands must be
installed by toolsets/project Dockerfile, and provider credentials must be passed
explicitly. Configured relative mount sources, including Claude paths, resolve
from the target workspace. Avoid storing credential-bearing files in Git.

### Infrastructure toolsets

`terraform` installs Terraform 1.16.3. `kubernetes-extras` adds kubectx/kubens
0.10.2 and stern 1.34.0 on top of the minimal `kubernetes` toolset. Both download
versioned upstream releases and verify embedded SHA256 checksums for Linux amd64
and arm64; unsupported architectures fail explicitly. Host kubeconfig/cloud
credentials are not mounted implicitly. Select only the tools you need:

```yaml
toolsets: [terraform, kubernetes-extras]
```

Offline executable checks can be run with `AGENTBOX_INFRA_TEST_IMAGE` pointing to
an image containing these toolsets and `pytest tests/test_infrastructure_toolsets.py`.

### Codex and Aider

```bash
agentbox run --agent codex ~/project
agentbox run --agent aider ~/project
```

Codex 0.154.0 and Aider 0.86.2 are installed only when selected. Neither mounts
host agent credentials or configuration by default; both use the private
workspace/agent HOME. Log in/configure the provider inside that environment, or
forward an explicit provider variable for batch use:

```bash
agentbox run --agent codex --non-interactive --env CODEX_API_KEY ~/project -- exec --model gpt-5.6-sol 'Summarize the project'
agentbox run --agent aider --non-interactive --env OPENAI_API_KEY ~/project -- --model openai/gpt-5.6-sol --message 'Summarize the project'
```

For Codex, `CODEX_API_KEY` supports noninteractive execution; see the
[official automation documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
Use `codex exec resume --last` to continue a saved session. If nested sandboxing
is unavailable, Codex's explicit `--dangerously-bypass-approvals-and-sandbox`
option relies on the agentbox container boundary; agentbox does not add it by
default. Aider provider options are documented in its
[usage guide](https://aider.chat/docs/usage.html); its project chat history remains
in the mounted workspace, and `--restore-chat-history` restores it. Agentbox
passes agent arguments through without changing model choices or Git behavior.

### Monorepo Dockerfiles

Select a Dockerfile inside the workspace explicitly:

```bash
agentbox run --dockerfile services/api/Dockerfile.agentbox ~/monorepo
agentbox build --dockerfile services/api/Dockerfile.agentbox
```

The equivalent setting is `project_dockerfile: services/api/Dockerfile.agentbox`.
The build context and `.dockerignore` stay at the workspace root, so COPY paths
remain workspace-relative. The selected file must exist and cannot escape the
workspace through `..`, absolute paths or symlinks. Without a selection, only the
workspace-root `Dockerfile.agentbox` is discovered. Files omit `FROM`; the chosen
path, instructions and base image contribute to the project image tag.

### Hermes gateway service

Configure Hermes provider access and messaging platforms in its private HOME
first (`agentbox run --agent hermes ~/project -- gateway setup`). Restrict allowed
senders using Hermes platform settings before accepting bot traffic. Agentbox
runs the foreground gateway under container supervision, without installing host
system services, sharing host bot credentials or publishing inbound ports.

```bash
agentbox service start ~/project --name project-bot --env OPENAI_API_KEY
agentbox service status project-bot
agentbox service logs project-bot --tail 100
agentbox service stop project-bot
```

Use `agentbox service --runtime docker ...` to select Docker explicitly. The
selected Docker context/DOCKER_HOST or Podman connection still applies. Gateway
containers are labelled; status/logs/stop refuse unrelated containers. Stop
removes the managed container but retains private HOME. To apply new credentials
or configuration, stop and start again. Start refuses HOME already used by an
active container; foreground Hermes sessions and gateways should not share it
concurrently. All service container arguments are built through the same mount,
UID and credential validation as foreground runs.

The default restart policy is `on-failure:3`; `--restart-policy unless-stopped`
opts into indefinite restart while the daemon is available. Host daemon startup
and user-session persistence remain host administration responsibilities. A
created/running container is not proof of bot readiness: inspect gateway logs and
verify the configured platform separately. Provider/bot tokens must be explicitly
configured or forwarded with `--env NAME`; platform configuration is never
inferred from host files. Logs are emitted by Hermes and may contain sensitive
application output. No authenticated third-party bot traffic is exercised by CI.

### Prebuilt images

Use a published Linux amd64 stack instead of building its toolsets locally:

```bash
agentbox run ~/project --image ghcr.io/vojtabiberle/agentbox:python
agentbox build --image ghcr.io/vojtabiberle/agentbox:python --rebuild
```

Or set `prebuilt_image: ghcr.io/vojtabiberle/agentbox:python` in configuration.
The `base`, `python` and `php` stacks all include Claude; the latter two add the
named language toolset. Match your configured toolsets/agent to the image: selecting
an image does not install missing tools. Mount/environment configuration still applies.
Hermes/Codex/Aider and custom toolsets currently use local builds or your own images.
Project Dockerfile extensions also work with prebuilt images.

An absent image is pulled; cached images are reused. `--rebuild` explicitly pulls
again, then rebuilds any project extension. Registry authentication uses the selected
container engine's normal login configuration. The published agentbox stacks support
anonymous pulls. For your own private registry images, authenticate with `podman login` or `docker login` first.

Publishing policy: weekly and manual builds update rolling `base`/`python`/`php`
tags. Release builds publish `vVERSION-STACK` tags. Every run also publishes a
unique `build-RUN_ID-ATTEMPT-STACK` tag and records its digest in the workflow summary.
Pin `ghcr.io/vojtabiberle/agentbox@sha256:...` for immutable deployments; rolling tags
receive upstream package/security updates. Builds smoke-test each stack before push
and pull the registry artifact for a second startup check. Images contain tools only;
no model or cloud credentials are provided to this workflow. ARM64 requires local
builds until a native ARM64 publishing/test runner is added.

### Diagnostics and preview

`agentbox doctor WORKSPACE --agent hermes` checks configuration, runtime connectivity,
mount sources, host directory permissions and the selected executable in a cached
base image. Its temporary check container has no host mounts, no network and a
read-only root. It does not test provider login or build project extensions.

`agentbox run WORKSPACE --dry-run` outputs a JSON access plan without creating HOME,
building/pulling images or starting containers. Environment values and agent argument
values are omitted; only names and argument count are shown. The base image is shown;
project extensions are resolved during execution. Required external mounts are still
validated. A missing workspace must be created explicitly before previewing.

### Scheduled integration coverage

The `Runtime Integration` GitHub Actions workflow runs weekly and on manual dispatch.
It builds the current Claude/Hermes/Codex/Aider toolsets, then checks real private HOME
persistence, state reset refusal, read-only mounts, stdin/exit codes, gateway lifecycle
and project image cache behavior on rootless Podman and standard Docker. Logs are
retained for 14 days, including build failures. No model/provider credentials or paid
model requests are used. Rootless Docker remains separately verified on a local daemon.

### Resource and network controls

```yaml
limits:
  memory: 2g
  cpus: 1.5
  pids_limit: 256
  network: none
```

`run --memory 2g --cpus 1.5 --pids-limit 256 --network none` overrides the
corresponding configuration fields. Services inherit these settings from their
workspace configuration. Omitted limits keep engine defaults; `network: default`
keeps normal engine networking. `none` disables external network access, including
model APIs and package downloads; loopback remains available. Limits constrain the
running container, not image builds. Memory accepts positive bytes or b/k/m/g units;
CPU quotas must be positive and finite, PID limits positive integers. Unknown limit
keys are rejected. In YAML, quote a memory value expressed as a bare byte count.

Actual enforcement requires runtime/cgroup support. Engine errors are surfaced;
agentbox never silently drops requested limits. `--dry-run` includes resolved limits.

### Image compatibility and publication evidence

Prebuilt runs now check the selected agent and command-like `provides` inventory
entries before creating private HOME or launching the agent. Missing commands fail
with their names. Project extensions are built before this check, so they can install
additional tools. Commands must be available on the image's default PATH; descriptive
resources such as `xterm-ghostty terminfo` are excluded. Custom toolsets should declare
their required executable names in `provides`. The probe has no host mounts,
credentials or networking, runs unprivileged with a read-only root and a 30s timeout.
It verifies availability, not tool behavior or image trust.

Published stacks include RPM/npm version inventories, a CycloneDX SBOM and a Grype
vulnerability report in the workflow's `image-reports-STACK` artifacts (90-day retention).
Syft catalogs packages; Grype uses Fedora security data. Publication checks that
every installed RPM name/version appears in the SBOM and that scan metadata identifies
Fedora. Critical findings and scan/tool failures block publication. Other findings remain
in the reports and require assessment; they are not automatically waived or treated as
a clean bill of health. See [the dependency assessment](docs/SECURITY_ASSESSMENT.md).
Build provenance and SBOM attestations are signed with GitHub Actions identity and
pushed to GHCR. Rolling/release tags are promoted only after smoke tests, scan and
attestation succeed. Workflow actions and scanner versions are pinned.

Verify a digest-pinned image with GitHub CLI:

```bash
gh attestation verify oci://ghcr.io/vojtabiberle/agentbox@sha256:DIGEST --repo vojtabiberle/agentbox
```

Attestation verifies the producing repository/workflow, not absence of vulnerabilities.

### Always-on server preview

`agentbox server run WORKSPACE` uses `/etc/agentbox/server.yaml`, which must be
root-owned along with its ancestors and not writable by other users. It never loads
workspace configuration/plugins/Dockerfiles. The policy fixes the image digest,
command, workspace root and resource/time/output limits. Rootless Podman is required;
Docker is deliberately unsupported in this profile.

The server uses a read-only root filesystem, temporary HOME and no IP network. An optional
Unix-socket broker provides exact-host HTTPS access and a bounded Anthropic endpoint
without handing provider keys to the workload. `server broker` and `server review-once`
use separate root-owned policies. The reference controller can comment on assigned
PRs using a GitHub App or a restricted DEV token held in Secret Manager.

See [GCP deployment](deploy/gcp/README.md), the [example configuration](examples/scheduled-review/runner.example.tfvars.json)
and [threat model](docs/THREAT_MODEL.md).

The GCP image adds host-level runner UID egress denial (including metadata), no public
VM IP, IAP/OS Login, disabled password/root SSH, automatic OS updates and dedicated
runner/broker identities. These host controls come from the GCP image; invoking
`server run` alone does not configure them on an arbitrary host.

The broker keeps provider credentials out of workload files/environment and admits
requests against a durable daily reservation budget. This is **not billing
reconciliation or a universal cost cap**: reservations must cover the configured
model's worst-case request, and do not include VM/NAT/CI costs. Structured audit
events cover lifecycle, broker decisions and controller actions, not every agent tool
or syscall. See the deployment guide for limits, rotation and off-host log retention.

The reference systemd timer polls directly assigned review requests. Its controller
deduplicates repository/PR/head SHA, supplies only a bounded diff to Claude Code with
tools disabled, and rechecks the head before commenting. It does not clone/build/test
the repository, approve reviews, push branches or merge PRs. Failed or ambiguous runs
require operator inspection before retry. `agentbox-stop` persistently disables the
deployed services until an administrator explicitly clears the stop marker.

**Verification:** the 2026-09-17 DEV pilot built/booted the GCP image, tested IAP,
container and host network boundaries, stop across reboot, and a live one-shot PR
review through Secret Manager/GitHub/Anthropic. No comment was published. The pilot's
compute, disks, custom images and NAT resources were removed afterward; this is
deployment tooling, not an available hosted service. Rotation, scheduled publication
and the 15-minute onboarding target remain unverified end to end.

## Trademark

AgentBox™ is a trademark of Vojta Biberle. Forks and derived works must use a different name and branding.
