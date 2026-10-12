from pathlib import Path

import pytest

from agentbox.exceptions import ConfigError, RemoteError
from agentbox.remote_registry import RemoteHost, get_host, load_registry, save_host


def _host(**overrides: str) -> RemoteHost:
    values = {
        "ssh": "agent-runner",
        "repository": "git@github.com:org/repo.git",
        "base_dir": "/home/u/agentbox-remote/repo",
        "agent": "claude",
        "runtime": "docker",
    }
    values.update(overrides)
    return RemoteHost.model_validate(values)


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "remotes.yaml"
    save_host("vm", _host(), path)
    assert get_host("vm", path) == _host()
    assert get_host("vm", path).repo_dir == "/home/u/agentbox-remote/repo/repo"
    assert get_host("vm", path).worktrees_dir == "/home/u/agentbox-remote/repo/wt"


def test_save_preserves_other_hosts(tmp_path: Path) -> None:
    path = tmp_path / "remotes.yaml"
    save_host("a", _host(), path)
    save_host("b", _host(ssh="other"), path)
    assert set(load_registry(path)) == {"a", "b"}


def test_unknown_host_points_to_setup(tmp_path: Path) -> None:
    with pytest.raises(RemoteError, match="agentbox remote setup vm"):
        get_host("vm", tmp_path / "missing.yaml")


def test_relative_base_dir_rejected() -> None:
    with pytest.raises(ValueError, match="absolute"):
        _host(base_dir="relative/path")


def test_missing_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "remotes.yaml"
    path.write_text("remotes:\n  vm:\n    ssh: x\n")
    with pytest.raises(ConfigError, match="vm"):
        load_registry(path)


def test_invalid_remote_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        save_host("-bad", _host(), tmp_path / "remotes.yaml")


def test_non_mapping_document_rejected(tmp_path: Path) -> None:
    path = tmp_path / "remotes.yaml"
    path.write_text("- a\n- b\n")
    with pytest.raises(ConfigError, match="expected a mapping"):
        load_registry(path)


def test_non_mapping_remotes_rejected(tmp_path: Path) -> None:
    path = tmp_path / "remotes.yaml"
    path.write_text("remotes: just-a-string\n")
    with pytest.raises(ConfigError, match="'remotes' must be a mapping"):
        load_registry(path)
