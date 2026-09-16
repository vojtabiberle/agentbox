"""Agent implementations."""

from ..exceptions import UnknownAgentError
from .aider import AiderAgent
from .base import Agent
from .claude import ClaudeAgent
from .codex import CodexAgent
from .hermes import HermesAgent

_AGENTS: dict[str, type[Agent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
    "aider": AiderAgent,
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


__all__ = [
    "Agent",
    "AiderAgent",
    "ClaudeAgent",
    "CodexAgent",
    "HermesAgent",
    "get_agent",
    "list_agents",
]
