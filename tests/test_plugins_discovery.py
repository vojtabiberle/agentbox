"""Tests for plugin discovery."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agentbox.plugins.discovery import (
    discover_all_plugins,
    get_builtin_plugins_path,
    get_project_plugins_path,
    get_user_plugins_path,
    list_plugin_sources,
)


class TestGetBuiltinPluginsPath:
    """Tests for get_builtin_plugins_path function."""

    def test_returns_path(self) -> None:
        """get_builtin_plugins_path returns a Path."""
        path = get_builtin_plugins_path()
        assert isinstance(path, Path)

    def test_path_ends_with_builtin(self) -> None:
        """get_builtin_plugins_path returns path ending with 'builtin'."""
        path = get_builtin_plugins_path()
        assert path.name == "builtin"

    def test_builtin_path_exists(self) -> None:
        """Built-in plugins path should exist in the project."""
        path = get_builtin_plugins_path()
        assert path.exists()

    def test_builtin_path_contains_plugins(self) -> None:
        """Built-in plugins path should contain plugin directories."""
        path = get_builtin_plugins_path()
        # Should have at least the 'base' plugin
        assert (path / "base").exists()
        assert (path / "base" / "toolset.yaml").exists()


class TestGetUserPluginsPath:
    """Tests for get_user_plugins_path function."""

    def test_returns_path(self) -> None:
        """get_user_plugins_path returns a Path."""
        path = get_user_plugins_path()
        assert isinstance(path, Path)

    def test_path_in_home_config(self) -> None:
        """get_user_plugins_path returns path in ~/.config/agentbox/."""
        path = get_user_plugins_path()
        assert ".config" in str(path)
        assert "agentbox" in str(path)
        assert path.name == "plugins"

    def test_path_starts_with_home(self) -> None:
        """get_user_plugins_path returns path under home directory."""
        path = get_user_plugins_path()
        home = Path.home()
        assert str(path).startswith(str(home))


class TestGetProjectPluginsPath:
    """Tests for get_project_plugins_path function."""

    def test_returns_none_without_workspace(self) -> None:
        """get_project_plugins_path returns None when workspace is None."""
        path = get_project_plugins_path(None)
        assert path is None

    def test_returns_path_with_workspace(self, tmp_path: Path) -> None:
        """get_project_plugins_path returns path when workspace provided."""
        path = get_project_plugins_path(tmp_path)
        assert path is not None
        assert isinstance(path, Path)

    def test_path_under_workspace(self, tmp_path: Path) -> None:
        """get_project_plugins_path returns path under workspace."""
        path = get_project_plugins_path(tmp_path)
        assert path is not None
        assert str(path).startswith(str(tmp_path))

    def test_path_in_agentbox_dir(self, tmp_path: Path) -> None:
        """get_project_plugins_path returns path in .agentbox/plugins."""
        path = get_project_plugins_path(tmp_path)
        assert path is not None
        assert path.name == "plugins"
        assert path.parent.name == ".agentbox"


class TestDiscoverAllPlugins:
    """Tests for discover_all_plugins function."""

    def test_discovers_builtin_plugins(self) -> None:
        """discover_all_plugins finds built-in plugins."""
        result = discover_all_plugins()

        # Should find our built-in plugins
        assert "base" in result.plugins
        assert "python" in result.plugins
        assert "go" in result.plugins
        assert result.plugins["base"].origin == "builtin"

    def test_user_plugins_override_builtin(self, tmp_path: Path) -> None:
        """User plugins override built-in plugins with same name."""
        user_plugins = tmp_path / "user-plugins"
        user_plugins.mkdir()
        (user_plugins / "base").mkdir()
        (user_plugins / "base" / "toolset.yaml").write_text(
            "name: base\ndescription: User base override"
        )

        with patch(
            "agentbox.plugins.discovery.get_user_plugins_path",
            return_value=user_plugins,
        ):
            result = discover_all_plugins()

        assert result.plugins["base"].origin == "user"
        assert result.plugins["base"].manifest.description == "User base override"

    def test_project_plugins_override_all(self, tmp_path: Path) -> None:
        """Project plugins override both built-in and user plugins."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project_plugins = workspace / ".agentbox" / "plugins"
        project_plugins.mkdir(parents=True)
        (project_plugins / "base").mkdir()
        (project_plugins / "base" / "toolset.yaml").write_text(
            "name: base\ndescription: Project base override"
        )

        result = discover_all_plugins(workspace)

        assert result.plugins["base"].origin == "project"
        assert result.plugins["base"].manifest.description == "Project base override"

    def test_discovers_user_only_plugins(self, tmp_path: Path) -> None:
        """discover_all_plugins finds user-only plugins."""
        user_plugins = tmp_path / "user-plugins"
        user_plugins.mkdir()
        (user_plugins / "custom-tool").mkdir()
        (user_plugins / "custom-tool" / "toolset.yaml").write_text(
            "name: custom-tool\ndescription: User custom tool"
        )

        with patch(
            "agentbox.plugins.discovery.get_user_plugins_path",
            return_value=user_plugins,
        ):
            result = discover_all_plugins()

        assert "custom-tool" in result.plugins
        assert result.plugins["custom-tool"].origin == "user"
        # Built-in plugins should still be there
        assert "base" in result.plugins

    def test_discovers_project_only_plugins(self, tmp_path: Path) -> None:
        """discover_all_plugins finds project-only plugins."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        project_plugins = workspace / ".agentbox" / "plugins"
        project_plugins.mkdir(parents=True)
        (project_plugins / "project-tool").mkdir()
        (project_plugins / "project-tool" / "toolset.yaml").write_text(
            "name: project-tool\ndescription: Project-specific tool"
        )

        result = discover_all_plugins(workspace)

        assert "project-tool" in result.plugins
        assert result.plugins["project-tool"].origin == "project"

    def test_no_workspace_skips_project_plugins(self) -> None:
        """discover_all_plugins skips project plugins when no workspace."""
        result = discover_all_plugins(None)

        # Should still have built-in plugins
        assert "base" in result.plugins
        # All plugins should be either builtin or user
        for plugin in result.plugins.values():
            assert plugin.origin in ("builtin", "user")

    def test_nonexistent_user_dir_handled(self, tmp_path: Path) -> None:
        """discover_all_plugins handles nonexistent user plugins dir."""
        nonexistent = tmp_path / "nonexistent"

        with patch(
            "agentbox.plugins.discovery.get_user_plugins_path",
            return_value=nonexistent,
        ):
            result = discover_all_plugins()

        # Should still find built-in plugins
        assert "base" in result.plugins


class TestListPluginSources:
    """Tests for list_plugin_sources function."""

    def test_returns_list_of_tuples(self) -> None:
        """list_plugin_sources returns list of tuples."""
        sources = list_plugin_sources()
        assert isinstance(sources, list)
        assert all(isinstance(s, tuple) for s in sources)
        assert all(len(s) == 3 for s in sources)

    def test_includes_builtin_and_user(self) -> None:
        """list_plugin_sources includes builtin and user paths."""
        sources = list_plugin_sources()
        origins = [s[0] for s in sources]

        assert "builtin" in origins
        assert "user" in origins

    def test_includes_project_with_workspace(self, tmp_path: Path) -> None:
        """list_plugin_sources includes project path when workspace provided."""
        sources = list_plugin_sources(tmp_path)
        origins = [s[0] for s in sources]

        assert "project" in origins

    def test_excludes_project_without_workspace(self) -> None:
        """list_plugin_sources excludes project path without workspace."""
        sources = list_plugin_sources(None)
        origins = [s[0] for s in sources]

        assert "project" not in origins

    def test_builtin_exists_flag(self) -> None:
        """list_plugin_sources correctly reports builtin exists."""
        sources = list_plugin_sources()
        builtin = next(s for s in sources if s[0] == "builtin")

        # builtin path should exist in our project
        assert builtin[2] is True

    def test_source_tuple_structure(self) -> None:
        """list_plugin_sources returns (origin, path, exists) tuples."""
        sources = list_plugin_sources()

        for origin, path, exists in sources:
            assert isinstance(origin, str)
            assert isinstance(path, Path)
            assert isinstance(exists, bool)
