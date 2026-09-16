import os
import subprocess

import pytest

from agentbox.agents import get_agent
from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.execution import prepare_run
from agentbox.plugins import PluginManager


@pytest.mark.parametrize("name", ["codex", "aider"])
def test_agents_are_separate_from_host_state(name):
    agent = get_agent(name)
    assert agent.get_command() == [name]
    assert agent.get_mounts(Config()) == []
    manager = PluginManager()
    assert [p.manifest.name for p in manager.load(agent.get_required_toolsets())] == ["base", name]


@pytest.mark.skipif(not os.environ.get("AGENTBOX_ADDITIONAL_AGENTS_IMAGE"), reason="Set AGENTBOX_ADDITIONAL_AGENTS_IMAGE")
@pytest.mark.parametrize("name", ["codex", "aider"])
def test_real_agent_startup_and_home_restart(tmp_path, name):
    runtime = ContainerRuntime(os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"))
    config = Config(state_dir=tmp_path / "state")
    for script in [f'{name} --version; echo remembered > "$HOME/marker"',
                   f'{name} --help; test "$(cat "$HOME/marker")" = remembered']:
        spec = prepare_run(os.environ["AGENTBOX_ADDITIONAL_AGENTS_IMAGE"], tmp_path, [],
                           ["bash", "-ec", script], config, agent=get_agent(name), interactive=False)
        result = subprocess.run(runtime.build_command(spec), text=True, capture_output=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
