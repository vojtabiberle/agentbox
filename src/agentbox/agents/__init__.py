"""Agent implementations."""

from ..exceptions import UnknownAgentError
from .base import Agent
from .claude import ClaudeAgent
from .hermes import HermesAgent

_AGENTS: dict[str, type[Agent]] = {
    "claude": ClaudeAgent,
    "hermes": HermesAgent,
}


def get_agent(name: str) -> Agent:
    """Get an agent instance by name."""
    if name not in _AGENTS:
        raise UnknownAgentError(name, list(_AGENTS.keys()))

    return _AGENTS[name]()


def list_agents() -> list[str]:
    """List available agent names."""
    return list(_AGENTS.keys())


__all__ = ["Agent", "ClaudeAgent", "HermesAgent", "get_agent", "list_agents"]
