"""Hermes interactive CLI integration."""

from .base import Agent


class HermesAgent(Agent):
    name = "hermes"
    description = "Nous Research Hermes Agent"

    def get_command(self) -> list[str]:
        return ["hermes"]

    def get_required_toolsets(self) -> list[str]:
        return ["hermes"]
