"""Claude Code agent."""

from pathlib import Path

from ..config import Config
from ..plugins.models import MountConfig
from .base import Agent


class ClaudeAgent(Agent):
    """Claude Code agent configuration."""

    name = "claude"
    description = "Anthropic's Claude Code AI assistant"

    def get_command(self) -> list[str]:
        """Return the command to run Claude Code."""
        return ["claude", "--dangerously-skip-permissions"]

    def get_required_toolsets(self) -> list[str]:
        """Install Claude and its dependencies."""
        return ["claude"]

    def get_mounts(self, config: Config) -> list[MountConfig]:
        mounts = []
        if config.claude.share_host_config:
            for name in (".claude", ".claude.json"):
                mounts.append(
                    MountConfig(source=str(Path.home() / name), target=f"~/{name}", readonly=False)
                )
        for source, target in (
            (config.claude.global_claude_md, "~/.claude/CLAUDE.md"),
            (config.claude.plugins_dir, "~/.claude/plugins"),
        ):
            if source is not None:
                mounts.append(MountConfig(source=str(source), target=target))
        return mounts
