"""Claude Code agent."""

from .base import Agent


class ClaudeAgent(Agent):
    """Claude Code agent configuration."""

    name = "claude"
    description = "Anthropic's Claude Code AI assistant"

    def get_command(self) -> list[str]:
        """Return the command to run Claude Code."""
        return ["claude", "--dangerously-skip-permissions"]

    def get_required_toolsets(self) -> list[str]:
        """Claude requires Node.js (installed via base toolset)."""
        return ["base"]
