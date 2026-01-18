"""Tests for plugin loader."""

from pathlib import Path

import pytest

from agentbox.exceptions import PluginValidationError
from agentbox.plugins.loader import load_plugin, load_plugins_from_directory


class TestLoadPlugin:
    """Tests for load_plugin function."""

    def test_load_plugin_valid_yaml(self, tmp_path: Path) -> None:
        """load_plugin loads valid toolset.yaml."""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
name: test
description: Test plugin
dockerfile: |
  RUN echo test
priority: 50
"""
        )

        plugin = load_plugin(plugin_dir, "user")

        assert plugin.manifest.name == "test"
        assert plugin.manifest.description == "Test plugin"
        assert plugin.manifest.priority == 50
        assert plugin.origin == "user"
        assert plugin.source_path == plugin_dir

    def test_load_plugin_yml_extension(self, tmp_path: Path) -> None:
        """load_plugin falls back to .yml extension."""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yml").write_text(
            """
name: yml-test
description: YML extension test
"""
        )

        plugin = load_plugin(plugin_dir, "builtin")

        assert plugin.manifest.name == "yml-test"

    def test_load_plugin_with_mounts(self, tmp_path: Path) -> None:
        """load_plugin correctly parses mounts."""
        plugin_dir = tmp_path / "cloud-aws"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
name: cloud-aws
description: AWS support
mounts:
  - source: ~/.aws
    target: /home/user/.aws
    readonly: true
    description: AWS credentials
  - source: ~/.aws-config
    target: /home/user/.aws-config
    readonly: false
"""
        )

        plugin = load_plugin(plugin_dir, "builtin")

        assert len(plugin.manifest.mounts) == 2
        assert plugin.manifest.mounts[0].source == "~/.aws"
        assert plugin.manifest.mounts[0].readonly is True
        assert plugin.manifest.mounts[1].readonly is False

    def test_load_plugin_with_environment(self, tmp_path: Path) -> None:
        """load_plugin correctly parses environment variables."""
        plugin_dir = tmp_path / "env-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
name: env-plugin
environment:
  AWS_CONFIG_FILE: /home/user/.aws/config
  AWS_PROFILE: default
"""
        )

        plugin = load_plugin(plugin_dir, "user")

        assert plugin.manifest.environment["AWS_CONFIG_FILE"] == "/home/user/.aws/config"
        assert plugin.manifest.environment["AWS_PROFILE"] == "default"

    def test_load_plugin_with_dependencies(self, tmp_path: Path) -> None:
        """load_plugin correctly parses depends_on."""
        plugin_dir = tmp_path / "dependent"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
name: dependent
depends_on:
  - base
  - python
"""
        )

        plugin = load_plugin(plugin_dir, "project")

        assert plugin.manifest.depends_on == ["base", "python"]

    def test_load_plugin_missing_manifest_raises(self, tmp_path: Path) -> None:
        """load_plugin raises error when toolset.yaml missing."""
        plugin_dir = tmp_path / "empty-plugin"
        plugin_dir.mkdir()

        with pytest.raises(PluginValidationError) as exc_info:
            load_plugin(plugin_dir, "user")

        assert "missing toolset.yaml" in str(exc_info.value)

    def test_load_plugin_invalid_yaml_raises(self, tmp_path: Path) -> None:
        """load_plugin raises error for invalid YAML."""
        plugin_dir = tmp_path / "bad-yaml"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
name: test
  invalid: indentation
"""
        )

        with pytest.raises(PluginValidationError) as exc_info:
            load_plugin(plugin_dir, "user")

        assert "Invalid YAML" in str(exc_info.value)

    def test_load_plugin_empty_manifest_raises(self, tmp_path: Path) -> None:
        """load_plugin raises error for empty manifest."""
        plugin_dir = tmp_path / "empty-manifest"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text("")

        with pytest.raises(PluginValidationError) as exc_info:
            load_plugin(plugin_dir, "user")

        assert "Empty manifest" in str(exc_info.value)

    def test_load_plugin_invalid_schema_raises(self, tmp_path: Path) -> None:
        """load_plugin raises error for invalid manifest schema."""
        plugin_dir = tmp_path / "bad-schema"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
description: Missing required name field
priority: 50
"""
        )

        with pytest.raises(PluginValidationError) as exc_info:
            load_plugin(plugin_dir, "user")

        assert "Invalid manifest" in str(exc_info.value)

    def test_load_plugin_invalid_mount_raises(self, tmp_path: Path) -> None:
        """load_plugin raises error for invalid mount config."""
        plugin_dir = tmp_path / "bad-mount"
        plugin_dir.mkdir()
        (plugin_dir / "toolset.yaml").write_text(
            """
name: bad-mount
mounts:
  - source: ~/.test
    # missing target
"""
        )

        with pytest.raises(PluginValidationError):
            load_plugin(plugin_dir, "user")


class TestLoadPluginsFromDirectory:
    """Tests for load_plugins_from_directory function."""

    def test_load_plugins_from_directory_multiple(self, tmp_path: Path) -> None:
        """load_plugins_from_directory loads multiple plugins."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create plugin 1
        (plugins_dir / "python").mkdir()
        (plugins_dir / "python" / "toolset.yaml").write_text(
            "name: python\ndescription: Python"
        )

        # Create plugin 2
        (plugins_dir / "go").mkdir()
        (plugins_dir / "go" / "toolset.yaml").write_text("name: go\ndescription: Go")

        result = load_plugins_from_directory(plugins_dir, "builtin")

        assert len(result.plugins) == 2
        assert "python" in result.plugins
        assert "go" in result.plugins
        assert result.plugins["python"].manifest.description == "Python"
        assert result.plugins["go"].manifest.description == "Go"

    def test_load_plugins_from_directory_empty(self, tmp_path: Path) -> None:
        """load_plugins_from_directory returns empty result for empty dir."""
        plugins_dir = tmp_path / "empty"
        plugins_dir.mkdir()

        result = load_plugins_from_directory(plugins_dir, "user")

        assert result.plugins == {}
        assert result.errors == {}

    def test_load_plugins_from_directory_nonexistent(self, tmp_path: Path) -> None:
        """load_plugins_from_directory returns empty result for nonexistent dir."""
        result = load_plugins_from_directory(tmp_path / "nonexistent", "user")

        assert result.plugins == {}
        assert result.errors == {}

    def test_load_plugins_from_directory_skips_files(self, tmp_path: Path) -> None:
        """load_plugins_from_directory skips non-directory items."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a valid plugin
        (plugins_dir / "valid").mkdir()
        (plugins_dir / "valid" / "toolset.yaml").write_text("name: valid")

        # Create a file (not a directory)
        (plugins_dir / "readme.txt").write_text("Not a plugin")

        result = load_plugins_from_directory(plugins_dir, "user")

        assert len(result.plugins) == 1
        assert "valid" in result.plugins

    def test_load_plugins_from_directory_skips_hidden(self, tmp_path: Path) -> None:
        """load_plugins_from_directory skips hidden directories."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a valid plugin
        (plugins_dir / "visible").mkdir()
        (plugins_dir / "visible" / "toolset.yaml").write_text("name: visible")

        # Create a hidden directory
        (plugins_dir / ".hidden").mkdir()
        (plugins_dir / ".hidden" / "toolset.yaml").write_text("name: hidden")

        result = load_plugins_from_directory(plugins_dir, "user")

        assert len(result.plugins) == 1
        assert "visible" in result.plugins
        assert "hidden" not in result.plugins

    def test_load_plugins_from_directory_skips_pycache(self, tmp_path: Path) -> None:
        """load_plugins_from_directory skips __pycache__ directories."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a valid plugin
        (plugins_dir / "valid").mkdir()
        (plugins_dir / "valid" / "toolset.yaml").write_text("name: valid")

        # Create __pycache__
        (plugins_dir / "__pycache__").mkdir()

        result = load_plugins_from_directory(plugins_dir, "user")

        assert len(result.plugins) == 1
        assert "valid" in result.plugins

    def test_load_plugins_from_directory_tracks_invalid(self, tmp_path: Path) -> None:
        """load_plugins_from_directory tracks invalid plugins in errors."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a valid plugin
        (plugins_dir / "valid").mkdir()
        (plugins_dir / "valid" / "toolset.yaml").write_text("name: valid")

        # Create an invalid plugin (has manifest but missing required field)
        (plugins_dir / "invalid").mkdir()
        (plugins_dir / "invalid" / "toolset.yaml").write_text("description: no name")

        result = load_plugins_from_directory(plugins_dir, "user")

        assert len(result.plugins) == 1
        assert "valid" in result.plugins
        assert "invalid" in result.errors

    def test_load_plugins_from_directory_skips_dirs_without_manifest(
        self, tmp_path: Path
    ) -> None:
        """load_plugins_from_directory skips directories without toolset.yaml."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create a directory without toolset.yaml
        (plugins_dir / "no-manifest").mkdir()
        (plugins_dir / "no-manifest" / "readme.md").write_text("Just a readme")

        result = load_plugins_from_directory(plugins_dir, "user")

        assert len(result.plugins) == 0
        assert len(result.errors) == 0

    def test_load_plugins_from_directory_uses_manifest_name(
        self, tmp_path: Path
    ) -> None:
        """load_plugins_from_directory uses manifest name as key, not dir name."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Directory name differs from manifest name
        (plugins_dir / "my-dir").mkdir()
        (plugins_dir / "my-dir" / "toolset.yaml").write_text("name: actual-name")

        result = load_plugins_from_directory(plugins_dir, "user")

        assert "actual-name" in result.plugins
        assert "my-dir" not in result.plugins

    def test_load_plugins_tracks_error_by_manifest_name(
        self, tmp_path: Path
    ) -> None:
        """load_plugins_from_directory tracks errors by both dir and manifest name."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Directory name differs from manifest name, but has validation error
        (plugins_dir / "my-dir").mkdir()
        (plugins_dir / "my-dir" / "toolset.yaml").write_text(
            "name: actual-name\npriority: not-a-number"  # Invalid priority type
        )

        result = load_plugins_from_directory(plugins_dir, "user")

        # Error should be tracked by both directory name and manifest name
        assert "my-dir" in result.errors
        assert "actual-name" in result.errors
        # Both should reference the same error
        assert result.errors["my-dir"] is result.errors["actual-name"]
