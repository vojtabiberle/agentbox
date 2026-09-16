"""Run preparation and mount validation regressions."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agentbox.agents import get_agent
from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.exceptions import ConfigError
from agentbox.execution import prepare_run, resolve_mounts
from agentbox.git import GitWorktreeInfo
from agentbox.plugins.models import MountConfig

@pytest.fixture(autouse=True)
def standard_docker_daemon(monkeypatch):
    monkeypatch.setattr(ContainerRuntime, "is_rootless_docker", lambda self: False)



@pytest.fixture
def context(tmp_path, monkeypatch):
    home = tmp_path / "host"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return tmp_path, Config(state_dir=tmp_path / "state")


def test_missing_mounts_are_optional_unless_required(tmp_path):
    mount = MountConfig(source=str(tmp_path / "missing"), target="/data")
    assert resolve_mounts([mount]) == ()
    with pytest.raises(ConfigError, match="Required mount source"):
        resolve_mounts([mount.model_copy(update={"required": True})])


def test_mount_aliases_deduplicate_and_conflicts_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    first = MountConfig(source=str(tmp_path), target="~/data")
    same = first.model_copy(update={"target": str(tmp_path / "data/../data")})
    assert len(resolve_mounts([first, same])) == 1
    for update in ({"readonly": False}, {"source": "/tmp"}, {"relabel": False}):
        with pytest.raises(ConfigError, match="Conflicting mounts"):
            resolve_mounts([first, same.model_copy(update=update)])


@pytest.mark.parametrize("target", ["relative", "/data:rw"])
def test_invalid_mount_targets_fail(tmp_path, target):
    with pytest.raises(ConfigError, match="Invalid mount path"):
        resolve_mounts([MountConfig(source=str(tmp_path), target=target)])


def test_plugins_cannot_replace_workspace(context):
    workspace, config = context
    with pytest.raises(ConfigError, match="Conflicting mounts for /workspace"):
        prepare_run(
            "image",
            workspace,
            [],
            ["bash"],
            config,
            mounts=[
                MountConfig(source="/tmp", target="/workspace"),
            ],
        )


@pytest.mark.parametrize("outside", [False, True])
def test_git_mounts_preserve_host_paths(context, outside):
    workspace, config = context
    common = workspace / "repo/.git"
    git_dir = workspace / "separate" if outside else common / "worktrees/test"
    common.mkdir(parents=True)
    git_dir.mkdir(parents=True)
    info = GitWorktreeInfo(git_common_dir=common, git_dir=git_dir, needs_mount=True)
    spec = prepare_run("image", workspace, [], ["bash"], config, git_worktree=info)
    mounts = {m.source: m for m in spec.mounts}
    assert mounts[common].target == str(common)
    assert not mounts[common].readonly
    assert (git_dir in mounts) == outside


def test_missing_git_metadata_fails(context):
    workspace, config = context
    info = GitWorktreeInfo(
        git_common_dir=workspace / "missing",
        git_dir=workspace / "missing/wt",
        needs_mount=True,
    )
    with pytest.raises(ConfigError, match="Required mount source"):
        prepare_run("image", workspace, [], ["bash"], config, git_worktree=info)


@pytest.mark.parametrize("runtime_name", ["docker", "podman"])
def test_spec_snapshot_and_noninteractive_command(context, runtime_name):
    workspace, config = context
    mounts = [MountConfig(source=str(workspace), target="/data")]
    env = {"HERMES_HOME": "/home/user/.hermes"}
    spec = prepare_run(
        "image",
        workspace,
        [],
        ["hermes", "--help"],
        config,
        mounts=mounts,
        environment=env,
        interactive=False,
        agent=get_agent("hermes"),
    )
    mounts.clear()
    env.clear()
    with patch("subprocess.run"), patch("os.execvp") as execute:
        runtime = ContainerRuntime(runtime_name)
        cmd = runtime.build_command(spec)
        execute.assert_not_called()
    assert "-it" not in cmd
    assert "--uts=host" not in cmd
    assert not any("machine-id" in arg for arg in cmd)
    assert f"HERMES_HOME={Path.home()}/.hermes" in cmd
    assert any(m.target == "/data" for m in spec.mounts)
    assert cmd[-3:] == ["image", "hermes", "--help"]


def test_claude_identity_mount_is_not_relabelled(context):
    workspace, config = context
    spec = prepare_run("image", workspace, [], ["claude"], config, agent=get_agent("claude"))
    assert spec.share_hostname
    identity = [m for m in spec.mounts if m.target == "/etc/machine-id"]
    if Path("/etc/machine-id").exists():
        assert len(identity) == 1
        assert identity[0].readonly and not identity[0].relabel


def test_explicit_claude_file_must_exist(context):
    workspace, config = context
    config.claude.global_claude_md = workspace / "missing.md"
    with pytest.raises(ConfigError, match="Required mount source"):
        prepare_run("image", workspace, [], ["claude"], config, agent=get_agent("claude"))


def test_only_configured_mounts_expand_home_placeholder(context):
    workspace, config = context
    common = workspace / "home/user/repo/.git"
    common.mkdir(parents=True)
    info = GitWorktreeInfo(git_common_dir=common, git_dir=common, needs_mount=True)
    spec = prepare_run(
        "image",
        workspace,
        [],
        ["bash"],
        config,
        git_worktree=info,
        mounts=[MountConfig(source=str(workspace), target="/home/user/shared")],
    )
    assert any(m.target == str(common) for m in spec.mounts)
    assert any(m.target == str(Path.home() / "shared") for m in spec.mounts)
