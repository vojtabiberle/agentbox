import shlex
from collections.abc import Sequence

import pytest

from agentbox.exceptions import ConfigError, RemoteError
from agentbox.remote_registry import RemoteHost
from agentbox.remote_ssh import CommandResult, RemoteShell
from agentbox.remote_tasks import (
    TaskStatus,
    attach_task,
    list_tasks,
    start_task,
    stop_task,
    task_logs,
)
from tests.remote_fakes import FakeRunner, fail, out

HOST = RemoteHost(
    ssh="vm",
    repository="git@github.com:o/r.git",
    base_dir="/srv/ab/r",
    agent="claude",
    runtime="docker",
)
# sha256("/srv/ab/r")[:8]: names are scoped to the registration's base_dir.
SESSION = "agentbox-017054c5-"
CONTAINER = "agentbox-task-017054c5-"


def _shell(runner: FakeRunner) -> RemoteShell:
    return RemoteShell("vm", runner)


def _owned(**responses: CommandResult) -> FakeRunner:
    return FakeRunner({"display-message": out("/srv/ab/r/wt/a\n"), **responses})


def test_start_creates_worktree_and_session() -> None:
    runner = FakeRunner({"tmux has-session": fail("no session"), "test -e": fail("")})
    start_task(_shell(runner), HOST, "dmd-1", "roman/DMD-1", "claude", ["do it"])
    cmds = runner.remote_commands()
    assert "git -C /srv/ab/r/repo fetch origin roman/DMD-1" in cmds
    assert "git -C /srv/ab/r/repo worktree add /srv/ab/r/wt/dmd-1 roman/DMD-1" in cmds
    tmux = shlex.split(cmds[-1])
    assert tmux[:7] == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        SESSION + "dmd-1",
        "-c",
        "/srv/ab/r/wt/dmd-1",
    ]
    assert shlex.split(tmux[tmux.index(";") - 1]) == [
        "agentbox",
        "run",
        "/srv/ab/r/wt/dmd-1",
        "--agent",
        "claude",
        "--name",
        CONTAINER + "dmd-1",
        "--",
        "do it",
    ]


@pytest.mark.parametrize(
    ("task", "branch"),
    [
        ("-x", "main"),
        ("a;b", "main"),
        ("fix.1", "main"),
        ("a:b", "main"),
        ("ok", "-main"),
        ("ok", "a;rm -rf ~"),
        ("ok", "a b"),
    ],
)
def test_start_rejects_unsafe_names(task: str, branch: str) -> None:
    runner = FakeRunner()
    with pytest.raises(ConfigError):
        start_task(_shell(runner), HOST, task, branch, "claude", [])
    assert runner.calls == []


def test_start_refuses_running_task() -> None:
    runner = FakeRunner()  # has-session succeeds by default
    with pytest.raises(RemoteError, match="already running"):
        start_task(_shell(runner), HOST, "dmd-1", "main", "claude", [])


class PrefixTmuxRunner(FakeRunner):
    """tmux resolves `-t name` by prefix; only `-t =name` is exact."""

    sessions: tuple[str, ...] = (SESSION + "fix-2",)

    def __call__(
        self, argv: Sequence[str], *, input: str | None = None, tty: bool = False
    ) -> CommandResult:
        result = super().__call__(argv, input=input, tty=tty)
        cmd = shlex.split(self.calls[-1].remote)
        if cmd[:2] == ["tmux", "has-session"]:
            target = cmd[3]
            if target.startswith("="):
                hit = target[1:] in self.sessions
            else:
                hit = any(s.startswith(target) for s in self.sessions)
            return CommandResult(0 if hit else 1, "", "" if hit else "can't find session")
        if cmd[:2] == ["test", "-e"]:
            return fail("")
        return result


def test_start_ignores_session_with_same_prefix() -> None:
    runner = PrefixTmuxRunner()
    start_task(_shell(runner), HOST, "fix", "main", "claude", [])
    cmds = runner.remote_commands()
    assert cmds[0] == f"tmux has-session -t ={SESSION}fix"
    assert any(c.startswith(f"tmux new-session -d -s {SESSION}fix ") for c in cmds)


def test_start_keeps_pane_after_agent_exits() -> None:
    runner = _branch_runner()
    start_task(_shell(runner), HOST, "t", "main", "claude", [])
    last = shlex.split(runner.remote_commands()[-1])
    # One tmux invocation: a separate set-option call races an agent that exits at once.
    assert last[:5] == ["tmux", "new-session", "-d", "-s", SESSION + "t"]
    assert last[last.index(";") :] == [
        ";",
        "set-option",
        "-t",
        f"={SESSION}t:",
        "remain-on-exit",
        "on",
    ]


def test_attach_uses_exact_target() -> None:
    runner = FakeRunner()
    attach_task(_shell(runner), HOST, "fix")
    call = runner.calls[-1]
    assert call.tty is True
    assert call.remote == f"tmux attach -t ={SESSION}fix"


def test_start_refuses_existing_worktree() -> None:
    runner = FakeRunner({"tmux has-session": fail("")})  # test -e succeeds by default
    with pytest.raises(RemoteError, match="already exists"):
        start_task(_shell(runner), HOST, "dmd-1", "main", "claude", [])


def test_start_reports_missing_branch() -> None:
    runner = FakeRunner(
        {
            "tmux has-session": fail(""),
            "test -e": fail(""),
            "fetch": fail("couldn't find remote ref x"),
        }
    )
    with pytest.raises(RemoteError, match="couldn't find remote ref"):
        start_task(_shell(runner), HOST, "dmd-1", "x", "claude", [])


def _branch_runner(**responses: CommandResult) -> FakeRunner:
    return FakeRunner({"tmux has-session": fail(""), "test -e": fail(""), **responses})


def test_start_fresh_branch_is_created_by_worktree_add() -> None:
    runner = _branch_runner(**{"rev-parse --verify": fail("")})
    start_task(_shell(runner), HOST, "t", "feature", "claude", [])
    cmds = runner.remote_commands()
    assert "git -C /srv/ab/r/repo rev-parse --verify --quiet refs/heads/feature" in cmds
    assert not any("is-ancestor" in c or "branch -f" in c for c in cmds)
    assert "git -C /srv/ab/r/repo worktree add /srv/ab/r/wt/t feature" in cmds


def test_start_fast_forwards_stale_local_branch() -> None:
    runner = _branch_runner()
    start_task(_shell(runner), HOST, "t", "main", "claude", [])
    cmds = runner.remote_commands()
    ancestor = (
        "git -C /srv/ab/r/repo merge-base --is-ancestor refs/heads/main refs/remotes/origin/main"
    )
    forward = "git -C /srv/ab/r/repo branch -f main origin/main"
    add = "git -C /srv/ab/r/repo worktree add /srv/ab/r/wt/t main"
    fetch = "git -C /srv/ab/r/repo fetch origin main"
    assert cmds.index(fetch) < cmds.index(ancestor) < cmds.index(forward) < cmds.index(add)


def test_start_refuses_diverged_local_branch() -> None:
    runner = _branch_runner(**{"is-ancestor": fail("", 1)})
    with pytest.raises(RemoteError, match="has commits not on origin"):
        start_task(_shell(runner), HOST, "t", "main", "claude", [])
    cmds = runner.remote_commands()
    assert not any("branch -f" in c or "worktree add" in c for c in cmds)


@pytest.mark.parametrize(
    ("needle", "stderr"),
    [
        (
            "branch -f",
            "fatal: cannot force update the branch 'main' used by worktree at '/srv/ab/r/wt/fix'",
        ),
        ("worktree add", "fatal: 'main' is already used by worktree at '/srv/ab/r/wt/fix'"),
    ],
)
def test_start_names_task_holding_the_branch(needle: str, stderr: str) -> None:
    runner = _branch_runner(**{needle: fail(stderr, 128)})
    with pytest.raises(RemoteError, match="checked out by task fix"):
        start_task(_shell(runner), HOST, "t", "main", "claude", [])


def test_start_surfaces_git_stderr_for_foreign_worktree() -> None:
    stderr = "fatal: 'main' is already used by worktree at '/home/u/elsewhere'"
    runner = _branch_runner(**{"worktree add": fail(stderr, 128)})
    with pytest.raises(RemoteError, match="/home/u/elsewhere"):
        start_task(_shell(runner), HOST, "t", "main", "claude", [])


def test_list_combines_sessions_and_worktrees() -> None:
    runner = FakeRunner(
        {
            "list-panes": out(
                f"{SESSION}a 0\n{SESSION}c 1\nagentbox-00000000-d 0\nagentbox-e 0\nother 0\n"
            ),
            "ls -1": out("a\nb\nc\n"),
        }
    )
    assert list_tasks(_shell(runner), HOST) == [
        TaskStatus("a", "running"),
        TaskStatus("b", "stopped"),
        TaskStatus("c", "exited"),
    ]
    assert "tmux list-panes -a -F '#{session_name} #{pane_dead}'" in runner.remote_commands()


@pytest.mark.parametrize(
    "stderr",
    [
        "no server running on /tmp/tmux-1000/default",
        "error connecting to /tmp/tmux-1000/default (No such file or directory)",
    ],
)
def test_list_without_tmux_server_or_worktrees(stderr: str) -> None:
    runner = FakeRunner(
        {"list-panes": fail(stderr), "ls -1": fail("No such file", 2), "test -e": fail("", 1)}
    )
    assert list_tasks(_shell(runner), HOST) == []


def test_list_propagates_ssh_failure_from_tmux() -> None:
    runner = FakeRunner({"list-panes": fail("ssh: connect to host vm: Connection refused", 255)})
    with pytest.raises(RemoteError, match="Cannot list tmux sessions: ssh: connect"):
        list_tasks(_shell(runner), HOST)


def test_list_propagates_ssh_failure_from_worktree_listing() -> None:
    runner = FakeRunner(
        {
            "list-panes": out(""),
            "ls -1": fail("ssh: connect to host vm: Connection refused", 255),
            "test -e": fail("ssh: connect to host vm: Connection refused", 255),
        }
    )
    with pytest.raises(RemoteError, match="Cannot list /srv/ab/r/wt: ssh: connect"):
        list_tasks(_shell(runner), HOST)


def test_logs_capture_pane() -> None:
    runner = FakeRunner({"capture-pane": out("line\n")})
    assert task_logs(_shell(runner), HOST, "a", 50) == "line\n"
    assert f"tmux capture-pane -p -t ={SESSION}a: -S -50" in runner.remote_commands()


class ContainerRunner(FakeRunner):
    """Container listed by `ps -a` until `rm -f` succeeds (or forever if sticky)."""

    present: bool = True
    sticky: bool = False

    def __call__(
        self, argv: Sequence[str], *, input: str | None = None, tty: bool = False
    ) -> CommandResult:
        result = super().__call__(argv, input=input, tty=tty)
        cmd = self.calls[-1].remote
        if cmd.startswith("docker ps -a"):
            return out(f"{CONTAINER}a-old\n{CONTAINER}a\n" if self.present else "")
        if cmd.startswith("docker rm -f") and result.returncode == 0 and not self.sticky:
            self.present = False
        return result


def _container_runner(**responses: CommandResult) -> ContainerRunner:
    return ContainerRunner({"display-message": out("/srv/ab/r/wt/a\n"), **responses})


def test_stop_keeps_worktree_by_default() -> None:
    runner = _container_runner()
    stop_task(_shell(runner), HOST, "a", remove_worktree=False)
    cmds = runner.remote_commands()
    assert f"tmux kill-session -t ={SESSION}a" in cmds
    assert f"docker ps -a --filter name={CONTAINER}a --format '{{{{.Names}}}}'" in cmds
    assert f"docker rm -f {CONTAINER}a" in cmds
    assert not any("worktree remove" in c for c in cmds)


def test_stop_skips_absent_container() -> None:
    runner = _owned()
    stop_task(_shell(runner), HOST, "a", remove_worktree=False)
    assert not any(c.startswith("docker rm") for c in runner.remote_commands())


def test_stop_reports_container_removal_failure() -> None:
    runner = _container_runner(**{"docker rm -f": fail("permission denied")})
    with pytest.raises(RemoteError, match="Cannot remove container.*permission denied"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    assert not any("worktree remove" in c for c in runner.remote_commands())


def test_stop_reports_container_that_survives_removal() -> None:
    runner = _container_runner()
    runner.sticky = True
    with pytest.raises(RemoteError, match="still present"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=False)


def test_stop_reports_container_listing_failure() -> None:
    runner = _owned(**{"docker ps": fail("Cannot connect to the Docker daemon")})
    with pytest.raises(RemoteError, match="Cannot list docker containers"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=False)


def test_stop_reports_session_kill_failure() -> None:
    runner = _owned(**{"kill-session": fail("server exited unexpectedly")})
    with pytest.raises(RemoteError, match="Cannot stop tmux session.*server exited"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=False)


def test_stop_accepts_session_that_ended_before_kill() -> None:
    class EndedRunner(FakeRunner):
        def __call__(
            self, argv: Sequence[str], *, input: str | None = None, tty: bool = False
        ) -> CommandResult:
            result = super().__call__(argv, input=input, tty=tty)
            cmd = self.calls[-1].remote
            has_session = [c for c in self.remote_commands() if "has-session" in c]
            if "has-session" in cmd and len(has_session) > 1:
                return fail("can't find session")
            return result

    runner = EndedRunner(
        {"display-message": out("/srv/ab/r/wt/a\n"), "kill-session": fail("can't find session")}
    )
    stop_task(_shell(runner), HOST, "a", remove_worktree=False)


def test_stop_refuses_dirty_worktree() -> None:
    runner = _owned(**{"status --porcelain": out(" M file.py\n")})
    with pytest.raises(RemoteError, match="uncommitted"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    assert not any("worktree remove" in c for c in runner.remote_commands())


def test_stop_removes_clean_worktree() -> None:
    runner = _owned(**{"status --porcelain": out("")})
    stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    assert "git -C /srv/ab/r/repo worktree remove /srv/ab/r/wt/a" in runner.remote_commands()


def test_stop_inspects_ignored_files() -> None:
    runner = _owned(**{"status --porcelain": out("")})
    stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    assert "git -C /srv/ab/r/wt/a status --porcelain --ignored" in runner.remote_commands()


def test_stop_refuses_worktree_with_ignored_files() -> None:
    runner = _owned(**{"status --porcelain": out("!! .env\n!! out/\n")})
    with pytest.raises(RemoteError, match=r"ignored files \(\.env, out/\).*--discard-ignored"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    cmds = runner.remote_commands()
    assert not any(word in c for c in cmds for word in ("worktree remove", "kill-session"))


def test_stop_discards_ignored_files_on_request() -> None:
    runner = _owned(**{"status --porcelain": out("!! .env\n")})
    stop_task(_shell(runner), HOST, "a", remove_worktree=True, discard_ignored=True)
    assert "git -C /srv/ab/r/repo worktree remove /srv/ab/r/wt/a" in runner.remote_commands()


def test_stop_unknown_task_is_clear_error() -> None:
    runner = FakeRunner({"tmux has-session": fail(""), "test -d /srv/ab/r/wt/a": fail("")})
    with pytest.raises(RemoteError, match="Task a not found"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    cmds = runner.remote_commands()
    assert not any(word in c for c in cmds for word in ("kill-session", "rm -f", "status"))


def test_stop_without_worktree_still_stops_session() -> None:
    runner = _owned(**{"test -d /srv/ab/r/wt/a": fail("")})
    stop_task(_shell(runner), HOST, "a", remove_worktree=True)
    cmds = runner.remote_commands()
    assert f"tmux kill-session -t ={SESSION}a" in cmds
    assert not any("status --porcelain" in c or "worktree remove" in c for c in cmds)


def test_stop_refuses_session_of_another_registration() -> None:
    runner = FakeRunner({"display-message": out("/srv/other/wt/a\n")})
    with pytest.raises(RemoteError, match="runs in /srv/other/wt/a"):
        stop_task(_shell(runner), HOST, "a", remove_worktree=False)
    cmds = runner.remote_commands()
    assert f"tmux display-message -p -t ={SESSION}a: '#{{session_path}}'" in cmds
    assert not any(word in c for c in cmds for word in ("kill-session", "rm -f"))


def test_same_task_name_on_two_registrations_does_not_collide() -> None:
    other = HOST.model_copy(update={"base_dir": "/srv/ab/other"})
    runner = FakeRunner({"tmux has-session": fail(""), "test -e": fail("")})
    start_task(_shell(runner), HOST, "t", "main", "claude", [])
    start_task(_shell(runner), other, "t", "main", "claude", [])
    sessions = [shlex.split(c)[4] for c in runner.remote_commands() if "new-session" in c]
    assert len(set(sessions)) == 2
