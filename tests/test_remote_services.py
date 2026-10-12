import pytest

from agentbox.exceptions import ConfigError
from agentbox.remote_registry import RemoteHost
from agentbox.remote_services import (
    service_logs,
    service_status,
    setup_service,
    start_service,
    stop_service,
)
from agentbox.remote_ssh import RemoteShell
from tests.remote_fakes import FakeRunner, out

HOST = RemoteHost(
    ssh="vm",
    repository="git@github.com:o/r.git",
    base_dir="/srv/ab/r",
    agent="claude",
    runtime="docker",
)
ENV = "env AGENTBOX_CONFIG=/srv/ab/r/agentbox.yaml"


def test_setup_runs_gateway_setup_with_tty() -> None:
    runner = FakeRunner()
    setup_service(RemoteShell("vm", runner), HOST)
    call = runner.calls[-1]
    assert call.tty is True
    assert call.remote == f"{ENV} agentbox run /srv/ab/r/repo --agent hermes -- gateway setup"


def test_start_passes_policy_and_env_names() -> None:
    runner = FakeRunner({"service start": out("Created bot: abc\n")})
    result = start_service(
        RemoteShell("vm", runner), HOST, "bot", "unless-stopped", ["OPENAI_API_KEY"]
    )
    assert result == "Created bot: abc\n"
    assert runner.remote_commands()[-1] == (
        f"{ENV} agentbox service start /srv/ab/r/repo --name bot --restart-policy unless-stopped"
        " --env OPENAI_API_KEY"
    )


def test_status_logs_stop_pass_through() -> None:
    runner = FakeRunner({"service status": out("bot: running\n")})
    shell = RemoteShell("vm", runner)
    assert service_status(shell, HOST, "bot") == "bot: running\n"
    service_logs(shell, HOST, "bot", 20)
    stop_service(shell, HOST, "bot")
    assert runner.remote_commands()[1:] == [
        f"bash -c '\"$@\" 2>&1' _ {ENV} agentbox service logs bot --tail 20",
        f"{ENV} agentbox service stop bot",
    ]


def test_invalid_service_name_rejected_before_ssh() -> None:
    runner = FakeRunner()
    with pytest.raises(ConfigError):
        service_status(RemoteShell("vm", runner), HOST, "--all")
    assert runner.calls == []


def test_invalid_restart_policy_rejected() -> None:
    runner = FakeRunner()
    with pytest.raises(ConfigError):
        start_service(RemoteShell("vm", runner), HOST, "bot", "always", [])
    assert runner.calls == []
