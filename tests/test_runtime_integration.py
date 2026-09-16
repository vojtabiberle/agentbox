"""Opt-in real-container regression tests. See README for invocation."""

import os
import subprocess

import pytest

from agentbox.agents import get_agent
from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.execution import prepare_run
from agentbox.plugins import PluginManager

IMAGE = os.environ.get("AGENTBOX_TEST_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="Set AGENTBOX_TEST_IMAGE to a Hermes image")


def test_home_and_hermes_survive_container_restart(tmp_path, monkeypatch):
    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    agent = get_agent("hermes")
    plugins = PluginManager()
    plugins.load(agent.get_required_toolsets())
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = Config(state_dir=tmp_path / "state")

    def execute(_binary, command):
        # Tests have no interactive terminal; all other runtime arguments are real.
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr

    monkeypatch.setattr(os, "execvp", execute)

    def run(script, selected=agent, directory=workspace):
        runtime.run(
            prepare_run(
                IMAGE,
                directory,
                [],
                ["bash", "-ec", script],
                config,
                mounts=plugins.get_all_mounts() if selected.name == "hermes" else [],
                environment=plugins.get_all_environment() if selected.name == "hermes" else {},
                interactive=False,
                agent=selected,
            )
        )

    run(
        """
        test "$(id -u)" = """
        + str(0 if runtime.is_rootless_docker() else os.getuid())
        + """
        test "$PWD" = /workspace
        mkdir -p "$HOME/.cache/node/corepack/v1" "$HOME/.local/bin" "$HOME/.config"
        printf remembered > "$HOME/.cache/node/corepack/v1/marker"
        printf workspace > /workspace/marker
        hermes --help
        hermes config set terminal.backend local
        test -s "$HERMES_HOME/config.yaml"
    """
    )
    run("""
        test "$(cat "$HOME/.cache/node/corepack/v1/marker")" = remembered
        test -s "$HERMES_HOME/config.yaml"
        hermes config show
    """)
    run('test ! -e "$HOME/.cache/node/corepack/v1/marker"', selected=get_agent("claude"))
    other = tmp_path / "other"
    other.mkdir()
    run('test ! -e "$HOME/.cache/node/corepack/v1/marker"', directory=other)
    assert (workspace / "marker").read_text() == "workspace"


def test_corepack_yarn_cache_survives_restart(tmp_path, monkeypatch):
    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text('{"packageManager":"yarn@4.0.0"}')
    config = Config(state_dir=tmp_path / "state")

    def execute(_binary, command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr

    monkeypatch.setattr(os, "execvp", execute)
    for script in (
        'npm install --global --prefix "$HOME/.local" corepack@0.34.0 && corepack yarn --version',
        "COREPACK_ENABLE_NETWORK=0 corepack yarn --version",
    ):
        runtime.run(
            prepare_run(
                IMAGE,
                workspace,
                [],
                ["bash", "-ec", script],
                config,
                agent=get_agent("hermes"),
                interactive=False,
            )
        )


def test_state_reset_refuses_running_container(tmp_path):
    from agentbox.exceptions import ConfigError
    from agentbox.state import reset_state

    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    spec = prepare_run(
        IMAGE,
        tmp_path,
        [],
        ["sleep", "60"],
        Config(state_dir=tmp_path / "state"),
        interactive=False,
        agent=get_agent("hermes"),
    )
    cmd = runtime.build_command(spec)
    cmd.insert(2, "-d")
    started = subprocess.run(cmd, check=True, capture_output=True, text=True)
    container_id = started.stdout.strip()
    try:
        with pytest.raises(ConfigError, match="active container"):
            reset_state(spec.home, runtime.runtime)
        assert spec.home.is_dir()
    finally:
        subprocess.run([runtime.runtime, "rm", "-f", container_id], check=True, capture_output=True)
    reset_state(spec.home, runtime.runtime)
    assert not spec.home.exists()


def test_batch_stdin_exit_code_and_forwarded_env(tmp_path, monkeypatch):
    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    monkeypatch.setenv("AGENTBOX_SMOKE_VALUE", "forwarded")
    spec = prepare_run(
        IMAGE,
        tmp_path,
        [],
        ["bash", "-c", 'read line; printf "%s/%s" "$line" "$AGENTBOX_SMOKE_VALUE"; exit 42'],
        Config(state_dir=tmp_path / "state"),
        interactive=False,
        stdin=True,
        name=f"agentbox-batch-{os.getpid()}",
        forwarded_env=("AGENTBOX_SMOKE_VALUE",),
    )
    result = subprocess.run(
        runtime.build_command(spec), input="input\n", text=True, capture_output=True, timeout=60
    )
    assert result.returncode == 42
    assert result.stdout == "input/forwarded"


def test_explicit_mcp_mount_is_readonly(tmp_path):
    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    config_file = tmp_path / "mcp.json"
    config_file.write_text('{"mcpServers": {}}')
    config = Config(
        state_dir=tmp_path / "state",
        mcp_mounts=[
            {"source": "mcp.json", "target": "/workspace/.mcp.json"},
        ],
    )
    spec = prepare_run(
        IMAGE,
        tmp_path,
        [],
        [
            "bash",
            "-ec",
            "cat /workspace/.mcp.json; if echo changed > /workspace/.mcp.json; then exit 1; fi",
        ],
        config,
        interactive=False,
    )
    result = subprocess.run(runtime.build_command(spec), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert config_file.read_text() == '{"mcpServers": {}}'


def test_managed_service_lifecycle_retains_state(tmp_path):
    from agentbox.exceptions import ConfigError
    from agentbox.service import inspect_service, start_service, stop_service
    from agentbox.state import reset_state

    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    spec = prepare_run(
        IMAGE,
        tmp_path,
        [],
        ["bash", "-c", 'echo remembered > "$HOME/service-memory"; exec sleep 60'],
        Config(state_dir=tmp_path / "state"),
        agent=get_agent("hermes"),
        interactive=False,
        name=f"agentbox-service-test-{os.getpid()}",
    )
    start_service(runtime, spec, "no")
    try:
        assert inspect_service(runtime, spec.name)["State"]["Running"]
        with pytest.raises(ConfigError, match="active"):
            reset_state(spec.home, runtime.runtime)
    finally:
        stop_service(runtime, spec.name)
    assert (spec.home / "service-memory").read_text().strip() == "remembered"
    reset_state(spec.home, runtime.runtime)
