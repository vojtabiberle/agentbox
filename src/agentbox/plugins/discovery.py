"""Multi-path plugin discovery."""

from __future__ import annotations

from pathlib import Path

from agentbox.exceptions import PluginValidationError
from agentbox.plugins.loader import load_plugins_from_directory
from agentbox.plugins.models import LoadedPlugin


class DiscoveryResult:
    """Result of plugin discovery across all sources."""

    def __init__(self) -> None:
        self.plugins: dict[str, LoadedPlugin] = {}
        self.errors: dict[str, PluginValidationError] = {}


def get_builtin_plugins_path() -> Path:
    """Get path to built-in plugins directory."""
    return Path(__file__).parent / "builtin"


def get_user_plugins_path() -> Path:
    """Get path to user plugins directory (~/.config/agentbox/plugins/)."""
    return Path.home() / ".config" / "agentbox" / "plugins"


def get_project_plugins_path(workspace: Path | None = None) -> Path | None:
    """Get path to project plugins directory (<workspace>/.agentbox/plugins/).

    Args:
        workspace: Path to workspace directory. If None, returns None.

    Returns:
        Path to project plugins or None if workspace not specified
    """
    if workspace is None:
        return None
    return workspace / ".agentbox" / "plugins"


def discover_all_plugins(workspace: Path | None = None) -> DiscoveryResult:
    """Discover all plugins from all sources.

    Discovery paths (later overrides earlier):
    1. Built-in: src/agentbox/plugins/builtin/
    2. User: ~/.config/agentbox/plugins/
    3. Project: <workspace>/.agentbox/plugins/

    Args:
        workspace: Optional workspace path for project plugins

    Returns:
        DiscoveryResult with plugins and any validation errors
    """
    result = DiscoveryResult()

    # 1. Built-in plugins (lowest priority)
    builtin_path = get_builtin_plugins_path()
    builtin_result = load_plugins_from_directory(builtin_path, "builtin")
    result.plugins.update(builtin_result.plugins)
    result.errors.update(builtin_result.errors)

    # 2. User plugins (medium priority, overrides built-in)
    user_path = get_user_plugins_path()
    user_result = load_plugins_from_directory(user_path, "user")
    result.plugins.update(user_result.plugins)
    result.errors.update(user_result.errors)

    # 3. Project plugins (highest priority, overrides all)
    project_path = get_project_plugins_path(workspace)
    if project_path is not None:
        project_result = load_plugins_from_directory(project_path, "project")
        result.plugins.update(project_result.plugins)
        result.errors.update(project_result.errors)

    return result


def list_plugin_sources(workspace: Path | None = None) -> list[tuple[str, Path, bool]]:
    """List all plugin source directories with their status.

    Args:
        workspace: Optional workspace path for project plugins

    Returns:
        List of (origin, path, exists) tuples
    """
    sources: list[tuple[str, Path, bool]] = []

    builtin_path = get_builtin_plugins_path()
    sources.append(("builtin", builtin_path, builtin_path.exists()))

    user_path = get_user_plugins_path()
    sources.append(("user", user_path, user_path.exists()))

    project_path = get_project_plugins_path(workspace)
    if project_path is not None:
        sources.append(("project", project_path, project_path.exists()))

    return sources
