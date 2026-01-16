"""Tests for configuration loading."""

from pathlib import Path

import pytest
import yaml

from agentbox.config import Config, load_config, get_config_paths


def test_default_config() -> None:
    """Default config has sensible values."""
    config = Config()
    assert config.runtime == "podman"
    assert config.toolsets == ["base"]
    assert config.image_name == "agentbox"


def test_config_from_dict() -> None:
    """Config can be created from dict."""
    config = Config.model_validate({
        "runtime": "docker",
        "toolsets": ["base", "python", "go"],
    })
    assert config.runtime == "docker"
    assert config.toolsets == ["base", "python", "go"]


def test_credentials_config() -> None:
    """Credentials config defaults to all false."""
    config = Config()
    assert config.credentials.github is False
    assert config.credentials.azure is False
    assert config.credentials.aws is False
    assert config.credentials.gcloud is False


def test_config_paths_include_expected_locations() -> None:
    """Config paths include cwd and home directory locations."""
    paths = get_config_paths()
    path_strs = [str(p) for p in paths]

    assert any(".agentbox.yaml" in p for p in path_strs)
    assert any(".config/agentbox/config.yaml" in p for p in path_strs)


def test_load_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Config is loaded from YAML file."""
    config_file = tmp_path / ".agentbox.yaml"
    config_file.write_text(yaml.dump({
        "runtime": "docker",
        "toolsets": ["base", "rust"],
    }))

    # Monkeypatch cwd to tmp_path
    monkeypatch.chdir(tmp_path)

    config, config_path = load_config()
    assert config.runtime == "docker"
    assert config.toolsets == ["base", "rust"]
    assert config_path == config_file


def test_load_config_returns_none_path_when_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_config returns None path when no config file exists."""
    # Use empty tmp_path with no config files
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    config, config_path = load_config()
    assert config_path is None
    assert config.toolsets == ["base"]  # defaults
