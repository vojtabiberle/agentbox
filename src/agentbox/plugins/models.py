"""Pydantic models for the plugin system."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass


class MountConfig(BaseModel):
    """Configuration for a container mount."""

    source: str = Field(description="Source path on host (supports ~ expansion)")
    target: str = Field(description="Target path in container")
    readonly: bool = Field(default=True, description="Whether mount is read-only")
    description: str | None = Field(default=None, description="Human-readable description")


class ToolsetManifest(BaseModel):
    """Manifest for a toolset plugin."""

    name: str = Field(description="Unique toolset identifier")
    description: str = Field(default="", description="Human-readable description")
    dockerfile: str | None = Field(default=None, description="Dockerfile fragment to include")
    mounts: list[MountConfig] = Field(default_factory=list, description="Container mounts to add")
    environment: dict[str, str] = Field(
        default_factory=dict, description="Environment variables to set"
    )
    depends_on: list[str] = Field(
        default_factory=list, description="Other toolsets this depends on"
    )
    priority: int = Field(default=100, description="Sort priority (lower = earlier in Dockerfile)")


class LoadedPlugin(BaseModel):
    """A fully loaded plugin with source information."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: ToolsetManifest
    source_path: Path = Field(description="Path where plugin was loaded from")
    origin: str = Field(description="Origin type: 'builtin', 'user', or 'project'")
