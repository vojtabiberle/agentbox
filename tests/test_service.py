import json
from unittest.mock import MagicMock, patch

import pytest

from agentbox.config import Config
from agentbox.exceptions import ConfigError
from agentbox.execution import prepare_run
from agentbox.service import LABEL, inspect_service, start_service, stop_service
from agentbox.state import record_runtime


def test_unmanaged_containers_cannot_be_stopped():
    runtime = MagicMock(runtime="podman")
    with patch("subprocess.run") as run:
        run.return_value.stdout = json.dumps([{"Id": "other", "Config": {"Labels": {}}}])
        with pytest.raises(ConfigError, match="not an agentbox gateway"):
            stop_service(runtime, "other")
        assert run.call_count == 1


def test_stop_uses_verified_id_not_mutable_name():
    runtime = MagicMock(runtime="podman")
    with patch("subprocess.run") as run:
        run.return_value.stdout = json.dumps(
            [{"Id": "verified-id", "Config": {"Labels": {LABEL: "hermes"}}}]
        )
        stop_service(runtime, "gateway")
    assert run.call_args_list[1].args[0] == ["podman", "stop", "verified-id"]
    assert run.call_args_list[2].args[0] == ["podman", "rm", "verified-id"]


def test_service_rejects_bad_names_and_restart_policy(tmp_path):
    runtime = MagicMock(runtime="podman")
    with pytest.raises(ConfigError):
        inspect_service(runtime, "--all")
    spec = prepare_run(
        "image",
        tmp_path,
        [],
        ["sleep", "60"],
        Config(state_dir=tmp_path / "state"),
        interactive=False,
        name="gateway",
    )
    with pytest.raises(ConfigError):
        start_service(runtime, spec, "unexpected")


def test_default_docker_context_is_recorded(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    with patch("subprocess.run") as run:
        run.return_value.stdout = "rootless-context\n"
        record_runtime(home, "docker")
    record = json.loads(next(tmp_path.glob(".runtime-*.json")).read_text())
    assert record["environment"]["DOCKER_CONTEXT"] == "rootless-context"


def test_service_cli_dispatches_foreground_gateway(tmp_path):
    from click.testing import CliRunner
    from agentbox.cli import main

    with (
        patch(
            "agentbox.service_cli.load_config",
            return_value=(Config(state_dir=tmp_path / "state"), None),
        ),
        patch("agentbox.service_cli.ContainerRuntime"),
        patch("agentbox.service_cli.ImageBuilder") as builder,
        patch("agentbox.service_cli.start_service") as start,
    ):
        builder.return_value.ensure_image.return_value = "image"
        start.return_value = "container-id"
        result = CliRunner().invoke(main, ["service", "start", str(tmp_path), "--name", "gateway"])
    assert result.exit_code == 0, result.exception
    spec = start.call_args.args[1]
    assert spec.command == ("hermes", "gateway", "run", "--external-supervisor")
    assert not spec.interactive and spec.forwarded_env == ()
