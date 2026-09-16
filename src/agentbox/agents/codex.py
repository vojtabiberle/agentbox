"""OpenAI Codex CLI."""

from .base import Agent


class CodexAgent(Agent):
    name = "codex"
    description = "OpenAI Codex CLI"

    def get_command(self) -> list[str]:
        return ["codex"]

    def get_required_toolsets(self) -> list[str]:
        return ["codex"]
