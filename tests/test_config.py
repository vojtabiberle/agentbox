"""Tests for configuration loading."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agentbox.config import (
    Config,
    get_config_paths,
    get_global_config_path,
    get_project_config_path,
    load_config,
    save_global_config,
    save_project_config,
)


class TestDefaultConfig:
    """Tests for default configuration values."""

    def test_default_config(self) -> None:
        """Default config has sensible values."""
        config = Config()
        assert config.runtime == "podman"
        assert config.toolsets == ["base"]
        assert config.image_name == "agentbox"

    def test_credentials_config(self) -> None:
        """Credentials config defaults to all false."""
        config = Config()
        assert config.credentials.github is False
        assert config.credentials.azure is False
        assert config.credentials.aws is False
        assert config.credentials.gcloud is False
        assert config.credentials.ssh_agent is False

    def test_claude_config_defaults(self) -> None:
        """Claude config defaults to None paths."""
        config = Config()
        assert config.claude.global_claude_md is None
        assert config.claude.plugins_dir is None


class TestConfigValidation:
    """Tests for config validation."""

    def test_config_from_dict(self) -> None:
        """Config can be created from dict."""
        config = Config.model_validate({
            "runtime": "docker",
            "toolsets": ["base", "python", "go"],
        })
        assert config.runtime == "docker"
        assert config.toolsets == ["base", "python", "go"]

    def test_invalid_runtime_rejected(self) -> None:
        """Invalid runtime value raises ValidationError."""
        with pytest.raises(ValidationError):
            Config.model_validate({"runtime": "invalid-runtime"})

    def test_invalid_toolsets_type_rejected(self) -> None:
        """Non-list toolsets value raises ValidationError."""
        with pytest.raises(ValidationError):
            Config.model_validate({"toolsets": "not-a-list"})

    def test_invalid_credentials_type_rejected(self) -> None:
        """Invalid credentials type raises ValidationError."""
        with pytest.raises(ValidationError):
            Config.model_validate({"credentials": {"github": "not-a-bool"}})


class TestConfigPaths:
    """Tests for config path discovery."""

    def test_config_paths_include_expected_locations(self) -> None:
        """Config paths include cwd and home directory locations."""
        paths = get_config_paths()
        path_strs = [str(p) for p in paths]

        assert any(".agentbox.yaml" in p for p in path_strs)
        assert any(".agentbox.yml" in p for p in path_strs)
        assert any(".config/agentbox/config.yaml" in p for p in path_strs)

    def test_get_global_config_path(self) -> None:
        """Global config path is in ~/.config/agentbox/."""
        path = get_global_config_path()
        assert ".config/agentbox/config.yaml" in str(path)

    def test_get_project_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Project config path is .agentbox.yaml in cwd."""
        monkeypatch.chdir(tmp_path)
        path = get_project_config_path()
        assert path == tmp_path / ".agentbox.yaml"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_from_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config is loaded from YAML file."""
        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text(yaml.dump({
            "runtime": "docker",
            "toolsets": ["base", "rust"],
        }))

        monkeypatch.chdir(tmp_path)

        config, config_path = load_config()
        assert config.runtime == "docker"
        assert config.toolsets == ["base", "rust"]
        assert config_path == config_file

    def test_load_config_returns_none_path_when_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_config returns None path when no config file exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))

        config, config_path = load_config()
        assert config_path is None
        assert config.toolsets == ["base"]

    def test_load_config_with_empty_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty YAML file returns default config."""
        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text("")

        monkeypatch.chdir(tmp_path)

        config, config_path = load_config()
        assert config.runtime == "podman"
        assert config_path == config_file

    def test_load_config_yml_extension(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config loaded from .yml extension."""
        config_file = tmp_path / ".agentbox.yml"
        config_file.write_text(yaml.dump({"runtime": "docker"}))

        monkeypatch.chdir(tmp_path)

        config, config_path = load_config()
        assert config.runtime == "docker"
        assert config_path == config_file


class TestSaveGlobalConfig:
    """Tests for save_global_config function."""

    def test_save_global_config_creates_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_global_config creates config file."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        path = save_global_config()

        assert path.exists()
        assert "config.yaml" in str(path)

    def test_save_global_config_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_global_config creates parent directories."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        config_dir = tmp_path / ".config" / "agentbox"
        assert not config_dir.exists()

        save_global_config()

        assert config_dir.exists()

    def test_save_global_config_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_global_config writes valid YAML content."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        path = save_global_config()
        content = path.read_text()

        assert "runtime:" in content
        assert "toolsets:" in content
        assert "credentials:" in content


class TestSaveProjectConfig:
    """Tests for save_project_config function."""

    def test_save_project_config_creates_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_project_config creates config file in cwd."""
        monkeypatch.chdir(tmp_path)

        path = save_project_config()

        assert path.exists()
        assert path == tmp_path / ".agentbox.yaml"

    def test_save_project_config_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_project_config writes project-specific YAML content."""
        monkeypatch.chdir(tmp_path)

        path = save_project_config()
        content = path.read_text()

        assert "toolsets:" in content
        assert "project configuration" in content.lower()
