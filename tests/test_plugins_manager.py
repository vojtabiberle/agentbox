"""Tests for PluginManager."""

from pathlib import Path
from unittest.mock import patch

import pytest

from agentbox.exceptions import PluginDependencyError, PluginNotFoundError
from agentbox.plugins import PluginManager
from agentbox.plugins.models import LoadedPlugin, MountConfig, ToolsetManifest


def create_test_plugin(
    name: str,
    description: str = "",
    dockerfile: str | None = None,
    mounts: list[MountConfig] | None = None,
    environment: dict[str, str] | None = None,
    depends_on: list[str] | None = None,
    priority: int = 100,
    origin: str = "builtin",
) -> LoadedPlugin:
    """Helper to create test plugins."""
    manifest = ToolsetManifest(
        name=name,
        description=description,
        dockerfile=dockerfile,
        mounts=mounts or [],
        environment=environment or {},
        depends_on=depends_on or [],
        priority=priority,
    )
    return LoadedPlugin(
        manifest=manifest,
        source_path=Path(f"/test/plugins/{name}"),
        origin=origin,
    )


class TestPluginManagerInit:
    """Tests for PluginManager initialization."""

    def test_init_without_workspace(self) -> None:
        """PluginManager initializes without workspace."""
        manager = PluginManager()
        assert manager._workspace is None

    def test_init_with_workspace(self, tmp_path: Path) -> None:
        """PluginManager initializes with workspace."""
        manager = PluginManager(tmp_path)
        assert manager._workspace == tmp_path

    def test_discovers_builtin_plugins_on_init(self) -> None:
        """PluginManager discovers built-in plugins on initialization."""
        manager = PluginManager()
        available = manager.list_available()

        names = [p.manifest.name for p in available]
        assert "base" in names
        assert "python" in names


class TestPluginManagerListAvailable:
    """Tests for list_available method."""

    def test_list_available_returns_list(self) -> None:
        """list_available returns a list."""
        manager = PluginManager()
        available = manager.list_available()
        assert isinstance(available, list)

    def test_list_available_returns_loaded_plugins(self) -> None:
        """list_available returns LoadedPlugin instances."""
        manager = PluginManager()
        available = manager.list_available()

        for plugin in available:
            assert isinstance(plugin, LoadedPlugin)

    def test_list_available_includes_all_builtin(self) -> None:
        """list_available includes all built-in plugins."""
        manager = PluginManager()
        available = manager.list_available()
        names = [p.manifest.name for p in available]

        expected = [
            "base",
            "python",
            "go",
            "rust",
            "php",
            "cloud-aws",
            "cloud-azure",
            "cloud-gcloud",
            "docker",
        ]
        for name in expected:
            assert name in names


class TestPluginManagerGetPlugin:
    """Tests for get_plugin method."""

    def test_get_plugin_returns_plugin(self) -> None:
        """get_plugin returns the requested plugin."""
        manager = PluginManager()
        plugin = manager.get_plugin("base")

        assert plugin.manifest.name == "base"

    def test_get_plugin_not_found_raises(self) -> None:
        """get_plugin raises PluginNotFoundError for unknown plugin."""
        manager = PluginManager()

        with pytest.raises(PluginNotFoundError) as exc_info:
            manager.get_plugin("nonexistent")

        assert "nonexistent" in str(exc_info.value)

    def test_get_plugin_not_found_includes_available(self) -> None:
        """PluginNotFoundError includes list of available plugins."""
        manager = PluginManager()

        with pytest.raises(PluginNotFoundError) as exc_info:
            manager.get_plugin("nonexistent")

        assert "base" in str(exc_info.value)


class TestPluginManagerLoad:
    """Tests for load method."""

    def test_load_single_plugin(self) -> None:
        """load loads a single plugin."""
        manager = PluginManager()
        loaded = manager.load(["base"])

        assert len(loaded) == 1
        assert loaded[0].manifest.name == "base"

    def test_load_multiple_plugins(self) -> None:
        """load loads multiple plugins."""
        manager = PluginManager()
        loaded = manager.load(["base", "python", "go"])

        names = [p.manifest.name for p in loaded]
        assert "base" in names
        assert "python" in names
        assert "go" in names

    def test_load_resolves_dependencies(self) -> None:
        """load includes dependencies automatically."""
        manager = PluginManager()
        # python depends on base
        loaded = manager.load(["python"])

        names = [p.manifest.name for p in loaded]
        assert "base" in names
        assert "python" in names

    def test_load_dependency_order(self) -> None:
        """load returns plugins in dependency order (by priority)."""
        manager = PluginManager()
        loaded = manager.load(["python"])

        names = [p.manifest.name for p in loaded]
        # base has priority 10, python has priority 50
        # so base should come before python
        assert names.index("base") < names.index("python")

    def test_load_unknown_plugin_raises(self) -> None:
        """load raises PluginNotFoundError for unknown plugin."""
        manager = PluginManager()

        with pytest.raises(PluginNotFoundError):
            manager.load(["nonexistent"])

    def test_load_missing_dependency_raises(self) -> None:
        """load raises PluginDependencyError for missing dependency."""
        # Create a mock plugin that depends on a nonexistent plugin
        mock_plugins = {
            "orphan": create_test_plugin(
                "orphan",
                depends_on=["nonexistent"],
            ),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        with pytest.raises(PluginDependencyError) as exc_info:
            manager.load(["orphan"])

        assert "nonexistent" in str(exc_info.value)

    def test_load_deduplicates_dependencies(self) -> None:
        """load doesn't include the same dependency twice."""
        manager = PluginManager()
        # Both python and go depend on base
        loaded = manager.load(["python", "go"])

        names = [p.manifest.name for p in loaded]
        assert names.count("base") == 1

    def test_load_stores_loaded_plugins(self) -> None:
        """load stores loaded plugins internally."""
        manager = PluginManager()
        manager.load(["base"])

        assert len(manager._loaded) == 1


class TestPluginManagerDependencyResolution:
    """Tests for dependency resolution."""

    def test_transitive_dependencies(self) -> None:
        """Dependencies are resolved transitively."""
        mock_plugins = {
            "a": create_test_plugin("a", priority=10),
            "b": create_test_plugin("b", depends_on=["a"], priority=20),
            "c": create_test_plugin("c", depends_on=["b"], priority=30),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        loaded = manager.load(["c"])
        names = [p.manifest.name for p in loaded]

        assert names == ["a", "b", "c"]

    def test_diamond_dependency(self) -> None:
        """Diamond dependencies are handled correctly."""
        # a -> b, a -> c, b -> d, c -> d
        mock_plugins = {
            "d": create_test_plugin("d", priority=10),
            "b": create_test_plugin("b", depends_on=["d"], priority=20),
            "c": create_test_plugin("c", depends_on=["d"], priority=20),
            "a": create_test_plugin("a", depends_on=["b", "c"], priority=30),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        loaded = manager.load(["a"])
        names = [p.manifest.name for p in loaded]

        # d should appear only once
        assert names.count("d") == 1
        # d should come before b and c, which come before a
        assert names.index("d") < names.index("b")
        assert names.index("d") < names.index("c")
        assert names.index("b") < names.index("a")
        assert names.index("c") < names.index("a")


class TestPluginManagerGetDockerfileFragments:
    """Tests for get_dockerfile_fragments method."""

    def test_returns_list(self) -> None:
        """get_dockerfile_fragments returns a list."""
        manager = PluginManager()
        manager.load(["base"])

        fragments = manager.get_dockerfile_fragments()
        assert isinstance(fragments, list)

    def test_returns_fragments_from_loaded(self) -> None:
        """get_dockerfile_fragments returns fragments from loaded plugins."""
        manager = PluginManager()
        manager.load(["base"])

        fragments = manager.get_dockerfile_fragments()

        assert len(fragments) == 1
        assert "dnf install" in fragments[0]

    def test_fragments_include_comments(self) -> None:
        """get_dockerfile_fragments includes toolset comment."""
        manager = PluginManager()
        manager.load(["base"])

        fragments = manager.get_dockerfile_fragments()

        assert "# Toolset: base" in fragments[0]

    def test_skips_plugins_without_dockerfile(self) -> None:
        """get_dockerfile_fragments skips plugins without dockerfile."""
        mock_plugins = {
            "with-docker": create_test_plugin(
                "with-docker",
                dockerfile="RUN echo test",
            ),
            "without-docker": create_test_plugin(
                "without-docker",
                dockerfile=None,
            ),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        manager.load(["with-docker", "without-docker"])
        fragments = manager.get_dockerfile_fragments()

        assert len(fragments) == 1
        assert "echo test" in fragments[0]

    def test_multiple_fragments_in_order(self) -> None:
        """get_dockerfile_fragments returns fragments in load order."""
        manager = PluginManager()
        manager.load(["base", "python"])

        fragments = manager.get_dockerfile_fragments()

        # base comes before python due to priority
        assert "# Toolset: base" in fragments[0]
        assert "# Toolset: python" in fragments[1]


class TestPluginManagerGetAllMounts:
    """Tests for get_all_mounts method."""

    def test_returns_list(self) -> None:
        """get_all_mounts returns a list."""
        manager = PluginManager()
        manager.load(["base"])

        mounts = manager.get_all_mounts()
        assert isinstance(mounts, list)

    def test_returns_mounts_from_loaded(self) -> None:
        """get_all_mounts returns mounts from loaded plugins."""
        manager = PluginManager()
        manager.load(["cloud-aws"])

        mounts = manager.get_all_mounts()

        assert len(mounts) >= 1
        sources = [m.source for m in mounts]
        assert "~/.aws" in sources

    def test_aggregates_multiple_plugins(self) -> None:
        """get_all_mounts aggregates mounts from multiple plugins."""
        manager = PluginManager()
        manager.load(["cloud-aws", "cloud-azure"])

        mounts = manager.get_all_mounts()
        sources = [m.source for m in mounts]

        assert "~/.aws" in sources
        assert "~/.azure" in sources

    def test_empty_for_plugins_without_mounts(self) -> None:
        """get_all_mounts returns empty list for plugins without mounts."""
        mock_plugins = {
            "no-mounts": create_test_plugin("no-mounts"),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        manager.load(["no-mounts"])
        mounts = manager.get_all_mounts()

        assert mounts == []


class TestPluginManagerGetAllEnvironment:
    """Tests for get_all_environment method."""

    def test_returns_dict(self) -> None:
        """get_all_environment returns a dict."""
        manager = PluginManager()
        manager.load(["base"])

        env = manager.get_all_environment()
        assert isinstance(env, dict)

    def test_returns_environment_from_loaded(self) -> None:
        """get_all_environment returns env vars from loaded plugins."""
        manager = PluginManager()
        manager.load(["cloud-aws"])

        env = manager.get_all_environment()

        assert "AWS_CONFIG_FILE" in env

    def test_merges_multiple_plugins(self) -> None:
        """get_all_environment merges env vars from multiple plugins."""
        mock_plugins = {
            "env1": create_test_plugin(
                "env1",
                environment={"VAR1": "value1"},
            ),
            "env2": create_test_plugin(
                "env2",
                environment={"VAR2": "value2"},
            ),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        manager.load(["env1", "env2"])
        env = manager.get_all_environment()

        assert env["VAR1"] == "value1"
        assert env["VAR2"] == "value2"

    def test_later_plugins_override(self) -> None:
        """get_all_environment uses later plugin values for conflicts."""
        mock_plugins = {
            "first": create_test_plugin(
                "first",
                environment={"SHARED": "first-value"},
                priority=10,
            ),
            "second": create_test_plugin(
                "second",
                environment={"SHARED": "second-value"},
                priority=20,
            ),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        manager.load(["first", "second"])
        env = manager.get_all_environment()

        # second has higher priority (comes later), so its value wins
        assert env["SHARED"] == "second-value"

    def test_empty_for_plugins_without_environment(self) -> None:
        """get_all_environment returns empty dict when no env vars."""
        mock_plugins = {
            "no-env": create_test_plugin("no-env"),
        }

        with patch.object(
            PluginManager, "_refresh_available", lambda self: None
        ):
            manager = PluginManager()
            manager._available = mock_plugins

        manager.load(["no-env"])
        env = manager.get_all_environment()

        assert env == {}
