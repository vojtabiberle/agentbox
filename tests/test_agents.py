"""Tests for agent implementations."""

import pytest

from agentbox.agents import get_agent, list_agents, ClaudeAgent


def test_list_agents() -> None:
    """list_agents returns available agent names."""
    agents = list_agents()
    assert "claude" in agents


def test_get_agent_claude() -> None:
    """get_agent returns Claude agent."""
    agent = get_agent("claude")
    assert isinstance(agent, ClaudeAgent)


def test_get_agent_unknown() -> None:
    """get_agent raises for unknown agent."""
    with pytest.raises(ValueError, match="Unknown agent"):
        get_agent("unknown-agent")


def test_claude_agent_command() -> None:
    """Claude agent returns correct command."""
    agent = ClaudeAgent()
    cmd = agent.get_command()
    assert cmd == ["claude", "--dangerously-skip-permissions"]


def test_claude_agent_metadata() -> None:
    """Claude agent has name and description."""
    agent = ClaudeAgent()
    assert agent.name == "claude"
    assert "Claude" in agent.description
