# Remote tasks: submit agent runs from a laptop to an SSH host

Status: draft for review (2026-09-25)

## Goal

Let a developer start an agent task from their laptop that runs on an always-on
Linux host (for example a private GCP VM reachable over IAP SSH), then list,
attach to, inspect and stop it from the laptop. The laptop can be closed while the
task runs. A one-time setup wizard prepares and validates the host.

## Non-goals

- Transferring uncommitted or untracked laptop changes. A task starts from a branch
  that already exists on the remote Git origin.
- Handing off a live agent session from the laptop.
- Nested Docker/Compose inside the task container. Project checks that need it run
  in CI on the pull request.
- A queue or concurrency cap. Each `remote run` starts immediately.
- Changes to the `server` profile, broker, scheduled review or `deploy/gcp`.

## User-facing commands

```bash
agentbox remote setup <host> [--ssh DEST]             # wizard, re-runnable
agentbox remote doctor <host>                         # read-only validation
agentbox remote run <host> --name <task> --branch <branch> [--agent claude] [-- AGENT_ARGS...]
agentbox remote list <host>
agentbox remote attach <host> <task>
agentbox remote logs <host> <task> [--tail N]
agentbox remote stop <host> <task> [--remove-worktree]
```

`--ssh` sets the ssh destination for `setup`. Without it, a new (not yet registered)
remote uses `<host>` itself as the ssh destination; a registered remote's stored `ssh`
value is used unless `--ssh` overrides it.

Long-running agent services (the existing `agentbox service` lifecycle, which is
Hermes-only) are managed the same way, but without any `--agent` flag:

```bash
agentbox remote service setup  <host>                                          # interactive: gateway setup
agentbox remote service start  <host> <name> [--restart-policy POLICY] [--env NAME ...]
agentbox remote service status <host> <name>
agentbox remote service logs   <host> <name> [--tail N]
agentbox remote service stop   <host> <name>
```

`service setup` takes only `<host>` — no service/container name. It runs
`agentbox run <base_dir>/repo --agent hermes -- gateway setup` interactively (an
allocated TTY, since the flow is interactive); this configures the per-repository
Hermes HOME, not a container, so it has nothing to name. `service start`/`status`/
`logs`/`stop` take a `<name>` and run the existing `agentbox service` commands on the
remote against `<base_dir>/repo`, with `<name>` passed through as the container name.
agentbox does not capture or store what the user enters during `gateway setup`.

`<host>` is a name registered by `remote setup`. It maps to an SSH destination
that is handed to `ssh` unchanged, so `~/.ssh/config` aliases, `ProxyCommand` (IAP)
and `ProxyJump` keep working.

## Laptop-side registry

`~/.config/agentbox/remotes.yaml`, written only by `remote setup`:

```yaml
remotes:
  agent-runner:
    ssh: agent-runner              # ssh destination, passed through verbatim
    repository: git@github.com:keboola/connection.git
    base_dir: /home/<user>/agentbox-remote/connection   # absolute path on the remote
    agent: claude                  # default agent for `remote run`
    runtime: docker                # podman or docker, detected by the wizard
```

All five keys are required. `remote setup` asks for `ssh`, `repository`, `base_dir`
and `agent`; `runtime` is detected (Podman preferred, falling back to Docker) rather
than asked. Other commands fail with an actionable error when the host is unknown or
a key is missing. The file contains no credentials.

## Remote layout

```
<base_dir>/repo/          # primary clone of `repository`
<base_dir>/wt/<task>/     # one git worktree per task
```

Each task runs in a tmux session named `agentbox-<task>` executing
`agentbox run <base_dir>/wt/<task> --agent <agent> --name agentbox-task-<task> -- AGENT_ARGS`.
Task names match `[a-zA-Z0-9][a-zA-Z0-9_-]*`: no dots or colons, since tmux rewrites
them in session names. Every tmux command addresses the session with an exact target
(`-t =agentbox-<task>`, and `=agentbox-<task>:` for `capture-pane`), so task `fix`
never matches session `agentbox-fix-2` by prefix. The session is created with
`remain-on-exit on`, so the pane and its output stay after the agent exits.

`remote list` reports one state per task:

- `running`: the tmux session exists and its pane is alive;
- `exited`: the tmux session exists but its pane is dead (the agent ended; `remote
  logs` still shows its output); `remote stop` is needed before reusing the name;
- `stopped`: the worktree exists without a tmux session.

The primary clone keeps a detached HEAD, so no branch (including the default branch)
is held by it and any branch can be checked out in a task worktree.

## Remote host requirements

The remote runs the local `run`/`service` profile, not the `server` profile:

- Linux with Podman or Docker usable by the SSH user without sudo.
- Outbound network access for the agent, Git, package registries and model APIs.
  The `deploy/gcp` module (deny-all egress, broker, baked image) is built for the
  `server` profile and is not a target for remote tasks.
- `git`, `tmux`, `pipx`, and `gh` logged in for the SSH user when tasks push or open PRs.

Membership in the `docker` group is root-equivalent on the host; use a dedicated host.

## Setup wizard (`remote setup <host>`)

Each step reports OK / FIXED / ACTION REQUIRED and the wizard stops at the first
step it cannot complete. Re-running skips satisfied steps.

1. **SSH**: `ssh -o BatchMode=yes <ssh> true`. On failure print the exact error and
   stop; the wizard never edits `~/.ssh/config`.
2. **Runtime**: detect Podman or Docker usable by the SSH user without sudo. If
   missing, print the distribution-specific install command and stop. The wizard
   never runs sudo.
3. **Tools**: require `git`, `tmux` and `pipx`; print install commands when missing.
4. **agentbox parity**: the remote must run the same version as the laptop. When the
   local agentbox runs from a source checkout, build a wheel from it, stream it to the
   remote base64-encoded over the existing SSH connection (stdin, not `scp`), and
   install it with `pipx`; otherwise install `agentbox==<local version>` with `pipx`.
   Verify `agentbox --version` matches. Asks for confirmation before installing or
   upgrading.
5. **GitHub**: check that `gh` is installed (otherwise `action`: install GitHub CLI
   from https://cli.github.com and re-run), then run `gh auth status` remotely. When not logged in, print the command
   the user runs in their own terminal (`ssh -t <ssh> gh auth login --web`). The
   wizard never reads, prints or transfers a token. With `gh auth login --web` (HTTPS
   credentials) the registered `repository` should be an HTTPS URL; an SSH URL needs
   a separate SSH key on the remote.
6. **Repository**: ask for `repository` and `base_dir`, then clone into
   `<base_dir>/repo` if absent and detach its HEAD (`git checkout --detach`); if
   present, verify its origin matches and detach a HEAD that is on a branch
   (reported as `fixed`; `remote doctor` reports it as `action` without changing it).
7. **Remote config**: settings needed are `runtime`, `credentials.github: true` and
   `state_scope: repository` (see below). agentbox loads the first config file it
   finds and never merges across files (repository-tracked `.agentbox.yaml`/`.yml`
   first, then the remote user's global `~/.config/agentbox/config.yaml`/`.yml` or
   `~/.agentbox.yaml`). If the repository tracks its own config, the wizard reads it
   and compares it with the required keys but never writes it, since a repo-tracked
   file always wins (worktrees do not carry untracked files from the primary clone):
   all keys present with the required values → `ok` and setup continues; otherwise
   `action` naming the file and only the missing or conflicting keys. Otherwise it adds any missing keys to the first
   existing global file,
   creating `~/.config/agentbox/config.yaml` only if none exists yet, after asking
   for confirmation. A key already present with a different value is reported as
   `action` and never overwritten. Malformed or non-mapping config (invalid YAML, a
   non-mapping document, a non-mapping `credentials`) is also reported as `action`,
   not a crash.
8. **Image**: run `agentbox build --agent <agent>` remotely so the first task does
   not wait for a build.
9. **Save** the registry entry.
10. **Agent login** (informational, does not block): print the command that logs the
    agent in once on the remote through a login shell, so pipx's `PATH` is loaded
    (`ssh -t <ssh> "bash -lc 'agentbox run <base_dir>/repo --agent <agent>'"`; the
    remote part is quoted with `shlex` twice because ssh re-joins its arguments). This is not verified automatically — agentbox does not inspect agent
    credentials — so this step always reports `info`, never `action`. Login state
    lives on the remote, shared by all worktrees of the repo.

`remote doctor` runs the checks of steps 1-7 and the step-10 login hint, without
changing anything and without a save step. Invalid wizard answers (for example a
non-absolute `base_dir`) are reported as `action`, not a crash.

## Shared agent state across worktrees

`state_home()` currently keys private HOME by the resolved workspace path, so each
worktree gets its own login. Add a config key:

```yaml
state_scope: workspace   # default, current behaviour
# state_scope: repository  -> key by the Git common directory
```

With `repository`, the digest input is the resolved Git common directory reported by
`git rev-parse --git-common-dir`, so the primary clone and all its worktrees share one
HOME per agent. Outside a Git repository `repository` is a configuration error, not a
silent fallback. Switching an existing setup to `repository` starts with a new,
empty HOME, so the agent needs a new login; `state reset` then deletes the HOME
shared by all worktrees of the repository. The existing lease and active-container checks keep working because
they operate on the resolved HOME path. `state show` reports the scope in use.

## Error handling

- Every remote step uses `ssh -o BatchMode=yes` and surfaces stderr verbatim.
- `run` rejects unknown options before `--`; everything after `--` is forwarded to
  the agent unchanged, including strings that look like flags.
- `run` refuses an existing task name (tmux session or worktree) instead of reusing it.
- `run` fails when `--branch` does not exist on the remote after `git fetch`.
- After the fetch, an existing local branch in the primary clone is fast-forwarded to
  `origin/<branch>` when it is an ancestor; a local branch with commits not on origin
  is refused ("push or delete it first"). A branch already checked out in another
  task's worktree is refused naming that task; for any other worktree, git's stderr
  is surfaced.
- `service logs` merges the container's stderr into the output (`2>&1` on the remote).
- `stop` without `--remove-worktree` keeps the worktree so work is not lost; with it,
  refuse when the worktree has uncommitted changes.
- No command prints environment values or file contents from the remote HOME.
- Invalid wizard answers and malformed or non-mapping remote config are reported as
  `action`, never raised as an unhandled error.

## Testing

- Unit tests with an injected command runner that records ssh invocations and
  returns scripted results: argument quoting, registry validation, each wizard step
  (OK / missing / failure), name validation, refusal paths.
- `state_scope` tests: shared HOME for two worktrees of one repository, distinct HOME
  for different repositories, error outside Git, default unchanged.
- Opt-in integration test (documented, not in default CI) against a real SSH host.
- `pytest`, `ruff check`, `ruff format --check`, `mypy` clean.

## Documentation

README section "Remote tasks", ROADMAP entry, CHANGELOG entry, AGENTS.md
architecture line for the new module.

## Manual acceptance

On a real host, after all automated tasks are complete:

1. `agentbox remote setup <host>` until all steps are OK/INFO; log the agent in once
   with the printed command.
2. `agentbox remote run <host> --name smoke --branch <existing-branch> -- "print the
   repo README title"`; `remote attach`, detach; close the laptop lid; reopen;
   `remote logs`.
3. `agentbox remote stop <host> smoke --remove-worktree`.
4. `agentbox remote service setup <host>`, then `remote service start <host> <name>
   --restart-policy unless-stopped`, `service status`, `service logs`; verify that
   `service logs` shows the gateway output.
5. With rootless Podman, verify the task survives SSH logout: `loginctl show-user
   $USER -p Linger` must report `Linger=yes`, otherwise the user's processes end at
   logout.
6. Start a task that fails immediately (for example an invalid agent argument); verify
   `remote list` shows it as `exited` and `remote logs` still shows its output.

## Open questions for the maintainer

- Is `state_scope: repository` acceptable in core, or should shared state stay
  opt-in through `claude.share_host_config` on the remote?
- Should `remote` live in core or as a plugin?
