from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from agentbox import __version__
from agentbox.cli import main
from agentbox.remote_registry import RemoteHost, save_host
from agentbox.remote_ssh import RemoteShell
from tests.remote_fakes import FakeRunner, fail, out


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    save_host(
        "vm",
        RemoteHost(
            ssh="vm",
            repository="git@github.com:o/r.git",
            base_dir="/srv/ab/r",
            agent="claude",
            runtime="docker",
        ),
    )
    return home


def _invoke(runner: FakeRunner, args: list[str]):  # type: ignore[no-untyped-def]
    with patch("agentbox.remote_cli.make_shell", lambda host: RemoteShell(host.ssh, runner)):
        return CliRunner().invoke(main, ["remote", *args])


def _new_session(runner: FakeRunner) -> str:
    return next(c for c in runner.remote_commands() if "tmux new-session" in c)


def test_run_uses_host_default_agent() -> None:
    runner = FakeRunner({"tmux has-session": fail(""), "test -e": fail("")})
    result = _invoke(runner, ["run", "vm", "--name", "t1", "--branch", "main", "--", "do it"])
    assert result.exit_code == 0, result.output
    assert "--agent claude" in _new_session(runner)


def test_run_rejects_unknown_option_before_separator() -> None:
    runner = FakeRunner()
    result = _invoke(
        runner,
        ["run", "vm", "--name", "t1", "--branch", "main", "--agnet", "hermes", "--", "do", "it"],
    )
    assert result.exit_code != 0
    assert "No such option" in result.output
    assert runner.calls == []


def test_run_passes_dashed_flag_after_separator_unchanged() -> None:
    runner = FakeRunner({"tmux has-session": fail(""), "test -e": fail("")})
    result = _invoke(
        runner,
        ["run", "vm", "--name", "t1", "--branch", "main", "--", "--dangerous-flag", "x"],
    )
    assert result.exit_code == 0, result.output
    assert "-- --dangerous-flag x" in _new_session(runner)


def test_list_prints_status() -> None:
    runner = FakeRunner(
        {
            "list-panes": out("agentbox-017054c5-t1 0\nagentbox-017054c5-t3 1\n"),
            "ls -1": out("t1\nt2\nt3\n"),
        }
    )
    result = _invoke(runner, ["list", "vm"])
    assert result.exit_code == 0
    assert result.output.splitlines() == ["t1\trunning", "t2\tstopped", "t3\texited"]


def test_list_without_tasks_says_so() -> None:
    runner = FakeRunner({"list-panes": fail("no server running"), "ls -1": fail("")})
    result = _invoke(runner, ["list", "vm"])
    assert result.exit_code == 0
    assert result.output.strip() == "No tasks on vm"


def test_unknown_host_is_clear_error() -> None:
    result = _invoke(FakeRunner(), ["list", "other"])
    assert result.exit_code != 0
    # `main` re-raises AgentboxError; the console entry point `cli` prints it.
    assert "agentbox remote setup other" in result.output + str(result.exception)


def test_doctor_exit_code_reflects_actions() -> None:
    runner = FakeRunner(
        {"gh auth status": fail("no"), "agentbox --version": out("agentbox, version 0\n")}
    )
    result = _invoke(runner, ["doctor", "vm"])
    assert result.exit_code == 1
    assert "ACTION" in result.output


def test_service_start_passes_policy() -> None:
    runner = FakeRunner()
    result = _invoke(
        runner, ["service", "start", "vm", "bot", "--restart-policy", "unless-stopped"]
    )
    assert result.exit_code == 0, result.output
    assert "--restart-policy unless-stopped" in runner.remote_commands()[-1]


def _healthy_setup_runner() -> FakeRunner:
    return FakeRunner(
        {
            "podman info": fail("no podman"),
            "agentbox --version": out(f"agentbox, version {__version__}\n"),
            "remote get-url origin": out("git@github.com:o/r.git\n"),
            "test -f /srv/ab/r/repo/.agentbox.yaml": fail(""),
            "test -f /srv/ab/r/repo/.agentbox.yml": fail(""),
            "cat .config/agentbox/config.yaml": out(
                yaml.safe_dump(
                    {
                        "runtime": "docker",
                        "credentials": {"github": True},
                        "state_scope": "repository",
                    }
                )
            ),
        }
    )


def test_setup_on_healthy_registered_host_exits_zero() -> None:
    runner = _healthy_setup_runner()
    with (
        patch("agentbox.remote_cli.RemoteShell", lambda dest: RemoteShell(dest, runner)),
        patch("agentbox.remote_cli.local_wheel", lambda: nullcontext(None)),
    ):
        result = CliRunner().invoke(main, ["remote", "setup", "vm"])
    assert result.exit_code == 0, result.output


def test_setup_rejects_invalid_remote_name_before_ssh() -> None:
    destinations: list[str] = []

    def factory(dest: str) -> RemoteShell:
        destinations.append(dest)
        return RemoteShell(dest, FakeRunner())

    with (
        patch("agentbox.remote_cli.RemoteShell", factory),
        patch("agentbox.remote_cli.local_wheel", lambda: nullcontext(None)),
    ):
        result = CliRunner().invoke(main, ["remote", "setup", "bad name", "--ssh", "vm"])
    assert result.exit_code != 0
    assert destinations == []


def test_setup_uses_explicit_ssh_destination_for_new_remote() -> None:
    destinations: list[str] = []

    def factory(dest: str) -> RemoteShell:
        destinations.append(dest)
        return RemoteShell(dest, FakeRunner({"true": fail("no route to host")}))

    with (
        patch("agentbox.remote_cli.RemoteShell", factory),
        patch("agentbox.remote_cli.local_wheel", lambda: nullcontext(None)),
    ):
        CliRunner().invoke(main, ["remote", "setup", "brand-new", "--ssh", "other-dest"])
    assert destinations == ["other-dest"]
