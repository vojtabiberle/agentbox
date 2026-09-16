from pathlib import Path

import pytest

from agentbox.config import Config
from agentbox.exceptions import ConfigError
from agentbox.execution import prepare_run
from agentbox.plugins import PluginManager


def test_toolset_source_override_is_required_and_workspace_relative(tmp_path):
    manager = PluginManager()
    manager.load(["cloud-aws"])
    original = manager.get_all_mounts()[0]
    mounts = manager.get_all_mounts({"cloud-aws": {"/home/user/.aws": Path("credentials")}}, tmp_path)
    assert mounts[0].source == str(tmp_path / "credentials")
    assert mounts[0].required and mounts[0].readonly
    assert original.source == "~/.aws" and not original.required


@pytest.mark.parametrize("overrides", [
    {"missing": {"/target": Path("source")}},
    {"cloud-aws": {"/wrong": Path("source")}},
])
def test_invalid_override_targets_fail(overrides):
    manager = PluginManager()
    manager.load(["cloud-aws"])
    with pytest.raises(ConfigError):
        manager.get_all_mounts(overrides)


def test_explicit_mcp_config_is_readonly_and_relative_to_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir("/tmp")
    (tmp_path / "mcp.json").write_text('{"mcpServers": {}}')
    config = Config(state_dir=tmp_path / "state", mcp_mounts=[
        {"source": "mcp.json", "target": "/workspace/.mcp.json"},
    ])
    spec = prepare_run("image", tmp_path, [], ["bash"], config)
    mount = next(m for m in spec.mounts if m.target == "/workspace/.mcp.json")
    assert mount.source == tmp_path / "mcp.json" and mount.readonly
    (tmp_path / "mcp.json").unlink()
    with pytest.raises(ConfigError, match="Required mount source"):
        prepare_run("image", tmp_path, [], ["bash"], config)


def test_no_mcp_sharing_by_default():
    assert Config().mcp_mounts == []
