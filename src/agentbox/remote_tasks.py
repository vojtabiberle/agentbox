"""Agent tasks on a remote host: one git worktree and one tmux session per task."""

from __future__ import annotations

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
_BRANCH = re.compile(r"[A-Za-z0-9._/-]+")
# tmux rewrites "." and ":" in session names, so task names exclude them.
_TASK = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
# git >= 2.42 says "used by worktree at", older versions "already checked out at".
_USED_BY_WORKTREE = re.compile(r"(?:worktree|checked out) at '([^']+)'")


@dataclass(frozen=True)
class TaskStatus:
    name: str
    state: Literal["running", "exited", "stopped"]


def session_name(task: str) -> str:
    return f"{SESSION_PREFIX}{task}"


def _target(task: str, *, pane: bool = False) -> str:
    # "=" disables tmux prefix matching; the trailing ":" makes a pane target exact too.
    return f"={session_name(task)}{':' if pane else ''}"


def container_name(task: str) -> str:
    return f"{CONTAINER_PREFIX}{task}"


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
    if shell.run(["tmux", "has-session", "-t", _target(task)]).returncode == 0:
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
            container_name(task),
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
            session_name(task),
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
            _target(task, pane=True),
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
    panes = shell.run(["tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_dead}"])
    alive: dict[str, bool] = {}
    for line in panes.stdout.splitlines() if panes.returncode == 0 else []:
        session, _, dead = line.rpartition(" ")
        if session.startswith(SESSION_PREFIX):
            task = session[len(SESSION_PREFIX) :]
            alive[task] = alive.get(task, False) or dead != "1"
    worktrees = shell.run(["ls", "-1", host.worktrees_dir])
    names = set(worktrees.stdout.split()) if worktrees.returncode == 0 else set()
    return [
        TaskStatus(name, "stopped" if name not in alive else "running" if alive[name] else "exited")
        for name in sorted(names | alive.keys())
    ]


def attach_task(shell: RemoteShell, task: str) -> int:
    _validate_task(task)
    return shell.interactive(["tmux", "attach", "-t", _target(task)])


def task_logs(shell: RemoteShell, task: str, tail: int) -> str:
    _validate_task(task)
    return shell.check(
        ["tmux", "capture-pane", "-p", "-t", _target(task, pane=True), "-S", f"-{tail}"],
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
    has_session = shell.run(["tmux", "has-session", "-t", _target(task)]).returncode == 0
    has_worktree = shell.run(["test", "-d", worktree]).returncode == 0
    if not has_session and not has_worktree:
        raise RemoteError(f"Task {task} not found on the remote (no tmux session, no worktree)")
    remove_worktree = remove_worktree and has_worktree
    if remove_worktree:
        _check_removable(shell, worktree, discard_ignored=discard_ignored)
    shell.run(["tmux", "kill-session", "-t", _target(task)])
    # Killing tmux may leave the foreground container running.
    shell.run([host.runtime, "rm", "-f", container_name(task)])
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
