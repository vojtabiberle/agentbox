"""Agent implementations."""

from .base import Agent
from .claude import ClaudeAgent


_AGENTS: dict[str, type[Agent]] = {
    "claude": ClaudeAgent,
}


def get_agent(name: str) -> Agent:
    """Get an agent instance by name."""
    if name not in _AGENTS:
        available = ", ".join(_AGENTS.keys())
        raise ValueError(f"Unknown agent: {name}. Available: {available}")

    return _AGENTS[name]()


def list_agents() -> list[str]:
    """List available agent names."""
    return list(_AGENTS.keys())


__all__ = ["Agent", "ClaudeAgent", "get_agent", "list_agents"]
