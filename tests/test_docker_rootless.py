"""Docker daemon UID mapping must match host bind-mount ownership."""
import os
import subprocess
from unittest.mock import patch

import pytest

from agentbox.container import ContainerRuntime
from agentbox.exceptions import ConfigError
from agentbox.execution import RunSpec


@pytest.mark.parametrize("options,user", [
    ('["name=rootless","name=seccomp,profile=builtin"]', "0:0"),
    ('["name=seccomp,profile=builtin"]', f"{os.getuid()}:{os.getgid()}"),
])
def test_docker_uid_mapping(options, user):
    with patch("subprocess.run") as run:
        run.return_value.stdout = options
        runtime = ContainerRuntime("docker")
        cmd = runtime.build_command(RunSpec("image", ("bash",), (), ()))
    assert cmd[cmd.index("--user") + 1] == user


@pytest.mark.parametrize("output", ["not json", "{}", "[1]"])
def test_invalid_daemon_response_fails_closed(output):
    with patch("subprocess.run") as run:
        run.return_value.stdout = output
        runtime = ContainerRuntime("docker")
        with pytest.raises(ConfigError):
            runtime.is_rootless_docker()


def test_unreachable_daemon_fails_closed():
    with patch("subprocess.run") as run:
        runtime = ContainerRuntime("docker")
        run.side_effect = subprocess.CalledProcessError(1, "docker info")
        with pytest.raises(ConfigError):
            runtime.is_rootless_docker()
