"""Opt-in real-container regression tests. See README for invocation."""

import os
import subprocess

import pytest

from agentbox.agents import get_agent
from agentbox.config import Config
from agentbox.container import ContainerRuntime
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
        command.remove("-it")
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr

    monkeypatch.setattr(os, "execvp", execute)

    def run(script, selected=agent, directory=workspace):
        runtime.run(
            IMAGE,
            directory,
            [],
            ["bash", "-ec", script],
            config,
            plugin_manager=plugins if selected.name == "hermes" else None,
            agent=selected,
        )

    run(
        """
        test "$(id -u)" = """
        + str(os.getuid())
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
        command.remove("-it")
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr

    monkeypatch.setattr(os, "execvp", execute)
    for script in (
        'npm install --global --prefix "$HOME/.local" corepack@0.34.0 && corepack yarn --version',
        "COREPACK_ENABLE_NETWORK=0 corepack yarn --version",
    ):
        runtime.run(
            IMAGE, workspace, [], ["bash", "-ec", script], config, agent=get_agent("hermes")
        )
