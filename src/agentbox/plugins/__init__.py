"""Plugin system for agentbox toolsets."""

from __future__ import annotations

from pathlib import Path

from agentbox.exceptions import (
    PluginDependencyError,
    PluginNotFoundError,
    PluginValidationError,
)
from agentbox.plugins.discovery import discover_all_plugins
from agentbox.plugins.models import LoadedPlugin, MountConfig, ToolsetManifest

__all__ = [
    "PluginManager",
    "LoadedPlugin",
    "MountConfig",
    "ToolsetManifest",
]


class PluginManager:
    """Manages plugin discovery, loading, and resolution."""

    def __init__(self, workspace: Path | None = None) -> None:
        """Initialize the plugin manager.

        Args:
            workspace: Optional workspace path for project-level plugins
        """
        self._workspace = workspace
        self._available: dict[str, LoadedPlugin] = {}
        self._invalid: dict[str, PluginValidationError] = {}
        self._loaded: list[LoadedPlugin] = []
        self._refresh_available()

    def _refresh_available(self) -> None:
        """Refresh the list of available plugins."""
        result = discover_all_plugins(self._workspace)
        self._available = result.plugins
        self._invalid = result.errors

    def list_available(self) -> list[LoadedPlugin]:
        """List all available plugins.

        Returns:
            List of available LoadedPlugin instances
        """
        return list(self._available.values())

    def get_plugin(self, name: str) -> LoadedPlugin:
        """Get a specific plugin by name.

        Args:
            name: Plugin name

        Returns:
            LoadedPlugin instance

        Raises:
            PluginNotFoundError: If plugin not found
            PluginValidationError: If plugin exists but has validation errors
        """
        if name not in self._available:
            # Check if this was an invalid plugin (had manifest but failed validation)
            if name in self._invalid:
                raise self._invalid[name]
            raise PluginNotFoundError(name, list(self._available.keys()))
        return self._available[name]

    def load(self, toolset_names: list[str]) -> list[LoadedPlugin]:
        """Load plugins by name, resolving dependencies.

        Args:
            toolset_names: List of toolset names to load

        Returns:
            List of LoadedPlugin instances in dependency order

        Raises:
            PluginNotFoundError: If a toolset is not found
            PluginValidationError: If a toolset has validation errors
            PluginDependencyError: If a dependency cannot be resolved
        """
        # First, validate all requested toolsets exist
        for name in toolset_names:
            if name not in self._available:
                # Check if this was an invalid plugin
                if name in self._invalid:
                    raise self._invalid[name]
                raise PluginNotFoundError(name, list(self._available.keys()))

        # Resolve dependencies and get ordered list
        resolved = self._resolve_dependencies(toolset_names)

        # Load plugins in resolved order
        self._loaded = [self._available[name] for name in resolved]
        return self._loaded

    def _resolve_dependencies(self, toolset_names: list[str]) -> list[str]:
        """Resolve dependencies and return toolsets in load order.

        Uses topological sort with priority as a tiebreaker. Dependencies
        always come before dependents, and among plugins at the same
        dependency level, lower priority values come first.

        Args:
            toolset_names: List of requested toolset names

        Returns:
            Ordered list of toolset names including dependencies

        Raises:
            PluginDependencyError: If a dependency cannot be resolved
        """
        # First pass: collect all plugins needed (including dependencies)
        needed: set[str] = set()
        visited_for_collection: set[str] = set()

        def collect(name: str, chain: list[str] | None = None) -> None:
            if chain is None:
                chain = []

            if name in visited_for_collection:
                return

            if name in chain:
                # Circular dependency detected
                cycle = " -> ".join(chain + [name])
                raise PluginDependencyError(name, f"circular dependency: {cycle}")

            if name not in self._available:
                # Find which plugin required this missing dependency
                requirer = chain[-1] if chain else "(root)"
                raise PluginDependencyError(requirer, name)

            visited_for_collection.add(name)
            needed.add(name)

            plugin = self._available[name]
            for dep in plugin.manifest.depends_on:
                collect(dep, chain + [name])

        for name in toolset_names:
            collect(name)

        # Second pass: Kahn's algorithm with priority-based selection
        # Build in-degree map (count of unmet dependencies)
        in_degree: dict[str, int] = {name: 0 for name in needed}
        for name in needed:
            plugin = self._available[name]
            for dep in plugin.manifest.depends_on:
                if dep in needed:
                    in_degree[name] += 1

        # Start with plugins that have no dependencies (in_degree == 0)
        # Use a list sorted by priority
        ready = [name for name in needed if in_degree[name] == 0]
        ready.sort(key=lambda n: self._available[n].manifest.priority)

        ordered: list[str] = []

        while ready:
            # Take the plugin with lowest priority from ready list
            current = ready.pop(0)
            ordered.append(current)

            # Find plugins that depend on current
            for name in needed:
                plugin = self._available[name]
                if current in plugin.manifest.depends_on:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        # Insert into ready list maintaining priority order
                        priority = self._available[name].manifest.priority
                        insert_idx = 0
                        for i, r in enumerate(ready):
                            if self._available[r].manifest.priority > priority:
                                break
                            insert_idx = i + 1
                        ready.insert(insert_idx, name)

        return ordered

    def get_dockerfile_fragments(self) -> list[str]:
        """Get Dockerfile fragments from loaded plugins in order.

        Returns:
            List of Dockerfile fragment strings
        """
        fragments: list[str] = []
        for plugin in self._loaded:
            if plugin.manifest.dockerfile:
                # Add a comment to identify the source
                comment = f"# Toolset: {plugin.manifest.name}"
                if plugin.manifest.description:
                    comment += f" - {plugin.manifest.description}"
                fragments.append(f"{comment}\n{plugin.manifest.dockerfile}")
        return fragments

    def get_all_mounts(self) -> list[MountConfig]:
        """Get all mount configurations from loaded plugins.

        Returns:
            List of MountConfig instances from all loaded plugins
        """
        mounts: list[MountConfig] = []
        for plugin in self._loaded:
            mounts.extend(plugin.manifest.mounts)
        return mounts

    def get_all_environment(self) -> dict[str, str]:
        """Get merged environment variables from loaded plugins.

        Later plugins override earlier ones.

        Returns:
            Dict of environment variable names to values
        """
        env: dict[str, str] = {}
        for plugin in self._loaded:
            env.update(plugin.manifest.environment)
        return env
