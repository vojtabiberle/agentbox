"""Tests for plugin models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from agentbox.plugins.models import LoadedPlugin, MountConfig, ToolsetManifest


class TestMountConfig:
    """Tests for MountConfig model."""

    def test_mount_config_required_fields(self) -> None:
        """MountConfig requires source and target."""
        mount = MountConfig(source="~/.aws", target="/home/user/.aws")
        assert mount.source == "~/.aws"
        assert mount.target == "/home/user/.aws"

    def test_mount_config_defaults(self) -> None:
        """MountConfig has correct defaults."""
        mount = MountConfig(source="~/.aws", target="/home/user/.aws")
        assert mount.readonly is True
        assert mount.description is None

    def test_mount_config_all_fields(self) -> None:
        """MountConfig accepts all fields."""
        mount = MountConfig(
            source="~/.config/gh",
            target="/home/user/.config/gh",
            readonly=False,
            description="GitHub CLI config",
        )
        assert mount.source == "~/.config/gh"
        assert mount.target == "/home/user/.config/gh"
        assert mount.readonly is False
        assert mount.description == "GitHub CLI config"

    def test_mount_config_from_dict(self) -> None:
        """MountConfig can be created from dict."""
        data = {
            "source": "~/.ssh",
            "target": "/home/user/.ssh",
            "readonly": True,
        }
        mount = MountConfig.model_validate(data)
        assert mount.source == "~/.ssh"

    def test_mount_config_missing_source_raises(self) -> None:
        """MountConfig raises error without source."""
        with pytest.raises(ValidationError):
            MountConfig(target="/home/user/.aws")  # type: ignore[call-arg]

    def test_mount_config_missing_target_raises(self) -> None:
        """MountConfig raises error without target."""
        with pytest.raises(ValidationError):
            MountConfig(source="~/.aws")  # type: ignore[call-arg]


class TestToolsetManifest:
    """Tests for ToolsetManifest model."""

    def test_manifest_required_fields(self) -> None:
        """ToolsetManifest requires name."""
        manifest = ToolsetManifest(name="python")
        assert manifest.name == "python"

    def test_manifest_defaults(self) -> None:
        """ToolsetManifest has correct defaults."""
        manifest = ToolsetManifest(name="test")
        assert manifest.description == ""
        assert manifest.dockerfile is None
        assert manifest.mounts == []
        assert manifest.environment == {}
        assert manifest.depends_on == []
        assert manifest.priority == 100

    def test_manifest_all_fields(self) -> None:
        """ToolsetManifest accepts all fields."""
        manifest = ToolsetManifest(
            name="cloud-aws",
            description="AWS CLI support",
            dockerfile="RUN dnf install -y awscli2",
            mounts=[
                MountConfig(source="~/.aws", target="/home/user/.aws"),
            ],
            environment={"AWS_CONFIG_FILE": "/home/user/.aws/config"},
            depends_on=["base"],
            priority=80,
        )
        assert manifest.name == "cloud-aws"
        assert manifest.description == "AWS CLI support"
        assert manifest.dockerfile == "RUN dnf install -y awscli2"
        assert len(manifest.mounts) == 1
        assert manifest.environment["AWS_CONFIG_FILE"] == "/home/user/.aws/config"
        assert manifest.depends_on == ["base"]
        assert manifest.priority == 80

    def test_manifest_from_dict(self) -> None:
        """ToolsetManifest can be created from dict (like YAML)."""
        data = {
            "name": "python",
            "description": "Python development",
            "dockerfile": "RUN dnf install -y python3",
            "depends_on": ["base"],
            "priority": 50,
            "mounts": [
                {"source": "~/.pypirc", "target": "/home/user/.pypirc"},
            ],
            "environment": {"PYTHONPATH": "/workspace"},
        }
        manifest = ToolsetManifest.model_validate(data)
        assert manifest.name == "python"
        assert manifest.depends_on == ["base"]
        assert len(manifest.mounts) == 1
        assert manifest.mounts[0].source == "~/.pypirc"

    def test_manifest_missing_name_raises(self) -> None:
        """ToolsetManifest raises error without name."""
        with pytest.raises(ValidationError):
            ToolsetManifest()  # type: ignore[call-arg]

    def test_manifest_invalid_mounts_type_raises(self) -> None:
        """ToolsetManifest raises error with invalid mounts type."""
        with pytest.raises(ValidationError):
            ToolsetManifest(name="test", mounts="invalid")  # type: ignore[arg-type]

    def test_manifest_invalid_environment_type_raises(self) -> None:
        """ToolsetManifest raises error with invalid environment type."""
        with pytest.raises(ValidationError):
            ToolsetManifest(name="test", environment=["invalid"])  # type: ignore[arg-type]


class TestLoadedPlugin:
    """Tests for LoadedPlugin model."""

    def test_loaded_plugin_required_fields(self) -> None:
        """LoadedPlugin requires manifest, source_path, and origin."""
        manifest = ToolsetManifest(name="test")
        plugin = LoadedPlugin(
            manifest=manifest,
            source_path=Path("/path/to/plugin"),
            origin="builtin",
        )
        assert plugin.manifest.name == "test"
        assert plugin.source_path == Path("/path/to/plugin")
        assert plugin.origin == "builtin"

    def test_loaded_plugin_accepts_path_object(self) -> None:
        """LoadedPlugin accepts Path objects."""
        manifest = ToolsetManifest(name="python")
        plugin = LoadedPlugin(
            manifest=manifest,
            source_path=Path("/usr/share/agentbox/plugins/python"),
            origin="builtin",
        )
        assert isinstance(plugin.source_path, Path)

    def test_loaded_plugin_different_origins(self) -> None:
        """LoadedPlugin accepts different origin types."""
        manifest = ToolsetManifest(name="custom")

        for origin in ["builtin", "user", "project"]:
            plugin = LoadedPlugin(
                manifest=manifest,
                source_path=Path("/path"),
                origin=origin,
            )
            assert plugin.origin == origin

    def test_loaded_plugin_preserves_manifest(self) -> None:
        """LoadedPlugin preserves full manifest data."""
        manifest = ToolsetManifest(
            name="complex",
            description="Complex plugin",
            dockerfile="RUN echo test",
            mounts=[MountConfig(source="~/.test", target="/test")],
            environment={"KEY": "value"},
            depends_on=["base", "python"],
            priority=25,
        )
        plugin = LoadedPlugin(
            manifest=manifest,
            source_path=Path("/plugins/complex"),
            origin="user",
        )
        assert plugin.manifest.name == "complex"
        assert plugin.manifest.description == "Complex plugin"
        assert plugin.manifest.priority == 25
        assert len(plugin.manifest.mounts) == 1
        assert plugin.manifest.depends_on == ["base", "python"]
