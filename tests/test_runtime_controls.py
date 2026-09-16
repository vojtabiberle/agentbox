from unittest.mock import patch

import pytest
from click.testing import CliRunner

from agentbox.cli import main
from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.exceptions import ConfigError
from agentbox.execution import prepare_run


def test_batch_name_and_env_forwarding_without_values_in_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_KEY", "secret-value")
    config = Config(state_dir=tmp_path / "state")
    spec = prepare_run(
        "image",
        tmp_path,
        [],
        ["bash"],
        config,
        interactive=False,
        stdin=True,
        name="task-1",
        forwarded_env=("MODEL_KEY",),
    )
    with patch("subprocess.run"):
        cmd = ContainerRuntime("podman").build_command(spec)
    assert "-i" in cmd and "-it" not in cmd
    assert cmd[cmd.index("--name") + 1] == "task-1"
    assert "MODEL_KEY" in cmd
    assert not any("secret-value" in arg for arg in cmd)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "--privileged"},
        {"name": "two names"},
        {"forwarded_env": ("KEY=value",)},
        {"forwarded_env": ("AGENTBOX_MISSING_TEST_KEY",)},
    ],
)
def test_invalid_run_controls_are_rejected(tmp_path, kwargs):
    with pytest.raises(ConfigError):
        prepare_run("image", tmp_path, [], ["bash"], Config(state_dir=tmp_path / "state"), **kwargs)


def test_cli_passes_run_controls(tmp_path):
    with (
        patch(
            "agentbox.cli.load_config", return_value=(Config(state_dir=tmp_path / "state"), None)
        ),
        patch("agentbox.cli.ContainerRuntime") as runtime,
        patch("agentbox.cli.ImageBuilder") as builder,
    ):
        builder.return_value.ensure_image.return_value = "image"
        result = CliRunner().invoke(
            main, ["run", "--non-interactive", "--name", "task-1", str(tmp_path)]
        )
    assert result.exit_code == 0, result.exception
    spec = runtime.return_value.run.call_args.args[0]
    assert spec.stdin and not spec.interactive and spec.name == "task-1"
