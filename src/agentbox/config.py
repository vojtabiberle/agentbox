"""Configuration management for agentbox."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class CredentialsConfig(BaseModel):
    """Credential sharing configuration."""

    github: bool = False
    azure: bool = False
    aws: bool = False
    gcloud: bool = False
    ssh_agent: bool = False


class ClaudeConfig(BaseModel):
    """Claude-specific configuration."""

    global_claude_md: Path | None = None
    plugins_dir: Path | None = None


class Config(BaseModel):
    """Main configuration model."""

    runtime: Literal["podman", "docker"] = "podman"
    toolsets: list[str] = Field(default_factory=lambda: ["base"])
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    image_name: str = "agentbox"


def get_config_paths() -> list[Path]:
    """Return list of config file paths to check, in priority order."""
    return [
        Path.cwd() / ".agentbox.yaml",
        Path.cwd() / ".agentbox.yml",
        Path.home() / ".config" / "agentbox" / "config.yaml",
        Path.home() / ".config" / "agentbox" / "config.yml",
        Path.home() / ".agentbox.yaml",
    ]


def load_config() -> tuple[Config, Path | None]:
    """Load configuration from file or return defaults.

    Returns:
        Tuple of (config, config_file_path or None if using defaults)
    """
    for path in get_config_paths():
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return Config.model_validate(data), path

    return Config(), None


def get_global_config_path() -> Path:
    """Return the global config file location."""
    return Path.home() / ".config" / "agentbox" / "config.yaml"


def get_project_config_path() -> Path:
    """Return the project config file location."""
    return Path.cwd() / ".agentbox.yaml"


def get_default_config_content(is_project: bool = False) -> str:
    """Return default config content.

    Args:
        is_project: If True, return project-specific config template
    """
    if is_project:
        return """\
# agentbox project configuration
# This file overrides the global config for this project
# See: https://github.com/vojtabiberle/agentbox

# Toolsets to include in the container image
# Available: base, php, python, go, rust, node, cloud-aws, cloud-azure, cloud-gcloud
toolsets:
  - base

# Project-specific credentials (overrides global)
# credentials:
#   github: true
#   aws: true

# Project-specific Claude settings
# claude:
#   # plugins_dir: ./.agentbox/plugins
"""
    else:
        return """\
# agentbox global configuration
# See: https://github.com/vojtabiberle/agentbox

# Container runtime: podman or docker
runtime: podman

# Default toolsets to include in the container image
# Available: base, php, python, go, rust, node, cloud-aws, cloud-azure, cloud-gcloud
toolsets:
  - base

# Credentials to share with the container
credentials:
  github: false    # ~/.config/gh
  azure: false     # ~/.azure
  aws: false       # ~/.aws
  gcloud: false    # ~/.config/gcloud
  ssh_agent: false # SSH_AUTH_SOCK forwarding

# Claude-specific settings
claude:
  # global_claude_md: ~/dotfiles/CLAUDE.md
  # plugins_dir: ~/dotfiles/claude-plugins
"""


def save_config(path: Path, is_project: bool = False) -> Path:
    """Create a config file at the specified path.

    Args:
        path: Path to save the config file
        is_project: If True, use project-specific template

    Returns:
        Path to the created config file
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(get_default_config_content(is_project))
    return path


def save_global_config() -> Path:
    """Create a default global config file."""
    return save_config(get_global_config_path(), is_project=False)


def save_project_config() -> Path:
    """Create a default project config file."""
    return save_config(get_project_config_path(), is_project=True)
