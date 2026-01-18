"""YAML loading and validation for plugins."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from agentbox.exceptions import PluginValidationError
from agentbox.plugins.models import LoadedPlugin, ToolsetManifest


def load_plugin(plugin_path: Path, origin: str) -> LoadedPlugin:
    """Load a plugin from a directory containing toolset.yaml.

    Args:
        plugin_path: Path to the plugin directory
        origin: Origin type ('builtin', 'user', or 'project')

    Returns:
        LoadedPlugin with manifest and metadata

    Raises:
        PluginValidationError: If manifest is missing or invalid
    """
    manifest_file = plugin_path / "toolset.yaml"

    if not manifest_file.exists():
        # Try .yml extension as fallback
        manifest_file = plugin_path / "toolset.yml"

    if not manifest_file.exists():
        raise PluginValidationError(f"Plugin directory '{plugin_path}' missing toolset.yaml")

    try:
        with open(manifest_file) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PluginValidationError(f"Invalid YAML in '{manifest_file}': {e}") from e

    if data is None:
        raise PluginValidationError(f"Empty manifest file: {manifest_file}")

    try:
        manifest = ToolsetManifest.model_validate(data)
    except ValidationError as e:
        raise PluginValidationError(f"Invalid manifest in '{manifest_file}': {e}") from e

    return LoadedPlugin(
        manifest=manifest,
        source_path=plugin_path,
        origin=origin,
    )


class PluginDiscoveryResult:
    """Result of plugin discovery from a directory."""

    def __init__(self) -> None:
        self.plugins: dict[str, LoadedPlugin] = {}
        self.errors: dict[str, PluginValidationError] = {}


def load_plugins_from_directory(plugins_dir: Path, origin: str) -> PluginDiscoveryResult:
    """Load all plugins from a directory.

    Args:
        plugins_dir: Directory containing plugin subdirectories
        origin: Origin type for all plugins in this directory

    Returns:
        PluginDiscoveryResult with valid plugins and any validation errors
    """
    result = PluginDiscoveryResult()

    if not plugins_dir.exists():
        return result

    for item in plugins_dir.iterdir():
        if not item.is_dir():
            continue

        # Skip hidden directories
        if item.name.startswith("."):
            continue

        # Skip __pycache__ and similar
        if item.name.startswith("__"):
            continue

        manifest_file = item / "toolset.yaml"
        manifest_file_yml = item / "toolset.yml"

        if manifest_file.exists() or manifest_file_yml.exists():
            try:
                plugin = load_plugin(item, origin)
                result.plugins[plugin.manifest.name] = plugin
            except PluginValidationError as e:
                # Track error by directory name
                result.errors[item.name] = e

                # Also try to extract manifest name and track error by that too
                # This handles the case where directory name differs from manifest name
                actual_manifest = manifest_file if manifest_file.exists() else manifest_file_yml
                try:
                    with open(actual_manifest) as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict) and "name" in data:
                        manifest_name = data["name"]
                        if manifest_name != item.name:
                            result.errors[manifest_name] = e
                except Exception:
                    # If we can't parse it, just use directory name
                    pass

    return result
