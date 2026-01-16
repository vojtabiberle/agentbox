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


def get_default_config_path() -> Path:
    """Return the default config file location."""
    return Path.home() / ".config" / "agentbox" / "config.yaml"


def save_default_config() -> Path:
    """Create a default config file."""
    path = get_default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    default_config = """\
# agentbox configuration
# See: https://github.com/vojtabiberle/agentbox

# Container runtime: podman or docker
runtime: podman

# Toolsets to include in the container image
# Available: base, php, python, go, rust, node, cloud-aws, cloud-azure, cloud-gcloud
toolsets:
  - base

# Credentials to share with the container
credentials:
  github: false    # ~/.config/gh
  azure: false     # ~/.azure
  aws: false       # ~/.aws
  gcloud: false    # ~/.config/gcloud
  ssh_agent: false # SSH_AUTH_SOCK (not yet implemented)

# Claude-specific settings
claude:
  # global_claude_md: ~/dotfiles/CLAUDE.md
  # plugins_dir: ~/dotfiles/claude-plugins
"""
    path.write_text(default_config)
    return path
