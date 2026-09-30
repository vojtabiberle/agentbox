"""Agent tasks on a remote host: one git worktree and one tmux session per task."""

from __future__ import annotations

import hashlib
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .exceptions import ConfigError, RemoteError
from .remote_registry import RemoteHost
from .remote_ssh import RemoteShell

SESSION_PREFIX = "agentbox-"
CONTAINER_PREFIX = "agentbox-task-"
SCOPE_LENGTH = 8
_BRANCH = re.compile(r"[A-Za-z0-9._/-]+")
# tmux rewrites "." and ":" in session names, so task names exclude them.
_TASK = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
# tmux without a running server: no socket yet, or a stale one.
_NO_TMUX_SERVER = ("no server running", "error connecting to")
# git >= 2.42 says "used by worktree at", older versions "already checked out at".
_USED_BY_WORKTREE = re.compile(r"(?:worktree|checked out) at '([^']+)'")


@dataclass(frozen=True)
class TaskStatus:
    name: str
    state: Literal["running", "exited", "stopped"]


def _scope(host: RemoteHost) -> str:
    # base_dir owns the clone and worktrees, so it separates registrations sharing one SSH host.
    return hashlib.sha256(host.base_dir.encode()).hexdigest()[:SCOPE_LENGTH]


def _session_prefix(host: RemoteHost) -> str:
    return f"{SESSION_PREFIX}{_scope(host)}-"


def session_name(host: RemoteHost, task: str) -> str:
    return f"{_session_prefix(host)}{task}"


def _target(host: RemoteHost, task: str, *, pane: bool = False) -> str:
    # "=" disables tmux prefix matching; the trailing ":" makes a pane target exact too.
    return f"={session_name(host, task)}{':' if pane else ''}"


def container_name(host: RemoteHost, task: str) -> str:
    return f"{CONTAINER_PREFIX}{_scope(host)}-{task}"


def _validate_task(task: str) -> None:
    if not _TASK.fullmatch(task):
        raise ConfigError(f"Invalid task name: {task}")


def _validate_branch(branch: str) -> None:
    if branch.startswith("-") or not _BRANCH.fullmatch(branch):
        raise ConfigError(f"Invalid branch name: {branch}")


def _worktree(host: RemoteHost, task: str) -> str:
    return f"{host.worktrees_dir}/{task}"


def start_task(
    shell: RemoteShell,
    host: RemoteHost,
    task: str,
    branch: str,
    agent: str,
    agent_args: Sequence[str],
) -> None:
    _validate_task(task)
    _validate_branch(branch)
    worktree = _worktree(host, task)
    if shell.run(["tmux", "has-session", "-t", _target(host, task)]).returncode == 0:
        raise RemoteError(f"Task {task} is already running or exited; stop it first")
    if shell.run(["test", "-e", worktree]).returncode == 0:
        raise RemoteError(
            f"Worktree {worktree} already exists; "
            "stop it with --remove-worktree or pick another name"
        )
    shell.check(
        ["git", "-C", host.repo_dir, "fetch", "origin", branch], error=f"Cannot fetch {branch}"
    )
    _sync_local_branch(shell, host, branch)
    _git_worktree_op(
        shell,
        host,
        ["git", "-C", host.repo_dir, "worktree", "add", worktree, branch],
        branch,
        error=f"Cannot create worktree for {branch}",
    )
    inner = shlex.join(
        [
            "agentbox",
            "run",
            worktree,
            "--agent",
            agent,
            "--name",
            container_name(host, task),
            "--",
            *agent_args,
        ]
    )
    shell.check(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session_name(host, task),
            "-c",
            worktree,
            "bash",
            "-lc",
            inner,
            # Same invocation, so the pane is kept even if the agent exits immediately.
            ";",
            "set-option",
            "-t",
            # remain-on-exit is a window option; a bare "=session" target is read as a window.
            _target(host, task, pane=True),
            "remain-on-exit",
            "on",
        ],
        error=f"Cannot start task {task}",
    )


def _git_worktree_op(
    shell: RemoteShell, host: RemoteHost, command: list[str], branch: str, *, error: str
) -> None:
    result = shell.run(command)
    if result.returncode == 0:
        return
    stderr = result.stderr.strip()
    match = _USED_BY_WORKTREE.search(stderr)
    path = match.group(1) if match else ""
    prefix = f"{host.worktrees_dir}/"
    if path.startswith(prefix) and "/" not in path[len(prefix) :]:
        raise RemoteError(f"Branch {branch} is already checked out by task {path[len(prefix) :]}")
    raise RemoteError(f"{error}: {stderr or f'exit {result.returncode}'}")


def _sync_local_branch(shell: RemoteShell, host: RemoteHost, branch: str) -> None:
    repo = host.repo_dir
    local = f"refs/heads/{branch}"
    if shell.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", local]).returncode != 0:
        return
    ancestor = shell.run(
        ["git", "-C", repo, "merge-base", "--is-ancestor", local, f"refs/remotes/origin/{branch}"]
    )
    if ancestor.returncode == 1:
        raise RemoteError(
            f"Local branch {branch} on the remote has commits not on origin; "
            "push or delete it first"
        )
    if ancestor.returncode != 0:
        detail = ancestor.stderr.strip() or f"exit {ancestor.returncode}"
        raise RemoteError(f"Cannot compare {branch} with origin/{branch}: {detail}")
    _git_worktree_op(
        shell,
        host,
        ["git", "-C", repo, "branch", "-f", branch, f"origin/{branch}"],
        branch,
        error=f"Cannot fast-forward {branch}",
    )


def list_tasks(shell: RemoteShell, host: RemoteHost) -> list[TaskStatus]:
    alive: dict[str, bool] = {}
    prefix = _session_prefix(host)
    for line in _pane_lines(shell):
        session, _, dead = line.rpartition(" ")
        if session.startswith(prefix):
            task = session[len(prefix) :]
            alive[task] = alive.get(task, False) or dead != "1"
    names = _worktree_names(shell, host)
    return [
        TaskStatus(name, "stopped" if name not in alive else "running" if alive[name] else "exited")
        for name in sorted(names | alive.keys())
    ]


def _pane_lines(shell: RemoteShell) -> list[str]:
    panes = shell.run(["tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_dead}"])
    if panes.returncode == 0:
        return panes.stdout.splitlines()
    if any(marker in panes.stderr for marker in _NO_TMUX_SERVER):
        return []
    detail = panes.stderr.strip() or f"exit {panes.returncode}"
    raise RemoteError(f"Cannot list tmux sessions: {detail}")


def _worktree_names(shell: RemoteShell, host: RemoteHost) -> set[str]:
    listing = shell.run(["ls", "-1", host.worktrees_dir])
    if listing.returncode == 0:
        return set(listing.stdout.split())
    # `test` exits 1 only for a missing path; ssh itself fails with 255.
    if shell.run(["test", "-e", host.worktrees_dir]).returncode == 1:
        return set()
    detail = listing.stderr.strip() or f"exit {listing.returncode}"
    raise RemoteError(f"Cannot list {host.worktrees_dir}: {detail}")


def attach_task(shell: RemoteShell, host: RemoteHost, task: str) -> int:
    _validate_task(task)
    return shell.interactive(["tmux", "attach", "-t", _target(host, task)])


def task_logs(shell: RemoteShell, host: RemoteHost, task: str, tail: int) -> str:
    _validate_task(task)
    return shell.check(
        ["tmux", "capture-pane", "-p", "-t", _target(host, task, pane=True), "-S", f"-{tail}"],
        error=f"Cannot read output of task {task}",
    )


def stop_task(
    shell: RemoteShell,
    host: RemoteHost,
    task: str,
    *,
    remove_worktree: bool,
    discard_ignored: bool = False,
) -> None:
    _validate_task(task)
    worktree = _worktree(host, task)
    has_session = shell.run(["tmux", "has-session", "-t", _target(host, task)]).returncode == 0
    has_worktree = shell.run(["test", "-d", worktree]).returncode == 0
    if not has_session and not has_worktree:
        raise RemoteError(f"Task {task} not found on the remote (no tmux session, no worktree)")
    if has_session:
        _check_owned(shell, host, task, worktree)
    remove_worktree = remove_worktree and has_worktree
    if remove_worktree:
        _check_removable(shell, worktree, discard_ignored=discard_ignored)
    if has_session:
        _kill_session(shell, host, task)
    # Killing tmux may leave the foreground container running.
    _remove_container(shell, host, task)
    if remove_worktree:
        shell.check(
            ["git", "-C", host.repo_dir, "worktree", "remove", worktree],
            error=f"Cannot remove {worktree}",
        )


def _check_removable(shell: RemoteShell, worktree: str, *, discard_ignored: bool) -> None:
    # `git worktree remove` deletes ignored files (.env, agent outputs) without asking.
    status = shell.check(
        ["git", "-C", worktree, "status", "--porcelain", "--ignored"],
        error=f"Cannot inspect {worktree}",
    )
    lines = [line for line in status.splitlines() if line.strip()]
    if any(not line.startswith("!! ") for line in lines):
        raise RemoteError(f"Worktree {worktree} has uncommitted changes; commit or push them first")
    ignored = [line[3:] for line in lines]
    if ignored and not discard_ignored:
        raise RemoteError(
            f"Worktree {worktree} has ignored files ({', '.join(ignored)}); "
            "remove them or pass --discard-ignored"
        )


def _check_owned(shell: RemoteShell, host: RemoteHost, task: str, worktree: str) -> None:
    path = shell.check(
        ["tmux", "display-message", "-p", "-t", _target(host, task, pane=True), "#{session_path}"],
        error=f"Cannot inspect task {task}",
    ).strip()
    if path != worktree:
        raise RemoteError(
            f"tmux session of task {task} runs in {path}, not {worktree}; not stopping"
        )


def _kill_session(shell: RemoteShell, host: RemoteHost, task: str) -> None:
    result = shell.run(["tmux", "kill-session", "-t", _target(host, task)])
    if result.returncode == 0:
        return
    # The agent may have ended the session between the check and the kill.
    if shell.run(["tmux", "has-session", "-t", _target(host, task)]).returncode == 1:
        return
    detail = result.stderr.strip() or f"exit {result.returncode}"
    raise RemoteError(f"Cannot stop tmux session of task {task}: {detail}")


def _container_exists(shell: RemoteShell, host: RemoteHost, name: str) -> bool:
    names = shell.check(
        [host.runtime, "ps", "-a", "--filter", f"name={name}", "--format", "{{.Names}}"],
        error=f"Cannot list {host.runtime} containers",
    )
    return name in names.split()


def _remove_container(shell: RemoteShell, host: RemoteHost, task: str) -> None:
    name = container_name(host, task)
    if not _container_exists(shell, host, name):
        return
    shell.check([host.runtime, "rm", "-f", name], error=f"Cannot remove container {name}")
    if _container_exists(shell, host, name):
        raise RemoteError(f"Container {name} is still present after removal")
