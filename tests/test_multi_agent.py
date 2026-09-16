"""Regression tests for isolated homes and agent selection."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agentbox.agents import get_agent
from agentbox.cli import main
from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.exceptions import ConfigError
from agentbox.image import ImageBuilder
from agentbox.plugins import PluginManager


@pytest.mark.parametrize("runtime_name", ["podman", "docker"])
def test_home_is_private_persistent_and_scoped(tmp_path, monkeypatch, runtime_name):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Existing host files must never be mounted implicitly.
    for name in (".cache", ".config", ".local", ".claude", ".hermes"):
        (tmp_path / name).mkdir()
    (tmp_path / ".claude.json").touch()
    config = Config(state_dir=tmp_path / "state")
    with patch("subprocess.run"), patch("os.execvp") as execute:
        runtime = ContainerRuntime(runtime_name)

        def run(workspace, agent):
            runtime.run("test-image", workspace, [], ["bash"], config, agent=get_agent(agent))
            command = execute.call_args.args[1]
            mounts = [command[i + 1] for i, arg in enumerate(command) if arg == "-v"]
            home_mount = next(m for m in mounts if m.startswith(str(config.state_dir)))
            source = Path(home_mount.split(":")[0])
            assert source.is_dir()
            assert source.stat().st_mode & 0o777 == 0o700
            assert f"HOME={tmp_path}" in command
            assert not any(
                m.startswith(f"{tmp_path}/{n}:")
                for m in mounts
                for n in (".cache", ".config", ".local", ".claude", ".claude.json", ".hermes")
            )
            return source

        home = run(tmp_path / "project", "hermes")
        (home / "memory").write_text("remember")
        assert run(tmp_path / "project", "hermes") == home
        assert (home / "memory").read_text() == "remember"
        assert run(tmp_path / "other-project", "hermes") != home
        assert run(tmp_path / "project", "claude") != home


def test_unwritable_state_fails_before_container_start(tmp_path):
    state = tmp_path / "file"
    state.touch()
    with patch("subprocess.run"), patch("os.execvp") as execute:
        runtime = ContainerRuntime("podman")
        with pytest.raises(ConfigError, match="Cannot create container HOME"):
            runtime.run("image", tmp_path, [], ["bash"], Config(state_dir=state))
        execute.assert_not_called()


@pytest.mark.parametrize("agent", ["claude", "hermes"])
def test_agent_dependencies_and_mounts_are_separate(agent):
    selected = get_agent(agent)
    manager = PluginManager()
    loaded = manager.load(selected.get_required_toolsets())
    assert [p.manifest.name for p in loaded] == ["base", agent]
    other = "hermes" if agent == "claude" else "claude"
    assert other not in [p.manifest.name for p in loaded]
    assert selected.get_mounts(Config()) == []
    if agent == "hermes":
        assert manager.get_all_environment()["TERMINAL_ENV"] == "local"
        assert manager.get_all_environment()["HERMES_HOME"].endswith("/.hermes")


@pytest.mark.parametrize("subcommand", ["run", "build"])
def test_cli_resolves_agent_before_build(tmp_path, monkeypatch, subcommand):
    monkeypatch.chdir(tmp_path)
    with (
        patch("agentbox.cli.load_config", return_value=(Config(), None)),
        patch("agentbox.cli.ContainerRuntime") as runtime,
        patch("agentbox.cli.ImageBuilder") as builder,
    ):
        builder.return_value.ensure_image.return_value = "image"
        args = [subcommand, "--agent", "hermes"]
        if subcommand == "run":
            args += [".", "--", "setup", "--help"]
        result = CliRunner().invoke(main, args)
        assert result.exit_code == 0, result.output
        assert builder.call_args.args[1].toolsets == ["base", "hermes"]
        if subcommand == "run":
            kwargs = runtime.return_value.run.call_args.kwargs
            assert kwargs["command"] == ["hermes", "setup", "--help"]
            assert kwargs["agent"].name == "hermes"


def test_unknown_agent_does_not_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with (
        patch("agentbox.cli.load_config", return_value=(Config(), None)),
        patch("agentbox.cli.ImageBuilder") as builder,
    ):
        result = CliRunner().invoke(main, ["run", "--agent", "unknown"])
        assert result.exit_code != 0
        builder.assert_not_called()


def test_global_images_change_when_agent_changes():
    names = []
    for agent in ("claude", "hermes"):
        builder = ImageBuilder(MagicMock(), Config(toolsets=[agent]))
        names.append(builder.ensure_image())
    assert names[0] != names[1]


def test_image_tag_handles_registry_port_and_existing_tag():
    builder = ImageBuilder(MagicMock(), Config(image_name="localhost:5000/team/agentbox:old"))
    assert builder._compute_image_name("FROM ubuntu") == "localhost:5000/team/agentbox:952b10c1"


def test_toolset_order_is_stable_for_image_hashes():
    manager = PluginManager()
    for requested in (["python", "go", "claude"], ["claude", "go", "python"]):
        assert [p.manifest.name for p in manager.load(requested)] == [
            "base",
            "go",
            "python",
            "claude",
        ]
