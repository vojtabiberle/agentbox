"""Aider coding assistant."""

from .base import Agent


class AiderAgent(Agent):
    name = "aider"
    description = "Aider coding assistant"

    def get_command(self) -> list[str]:
        return ["aider"]

    def get_required_toolsets(self) -> list[str]:
        return ["aider"]
