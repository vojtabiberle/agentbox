"""Tests for agent implementations."""

import pytest

from agentbox.agents import get_agent, list_agents, ClaudeAgent
from agentbox.exceptions import UnknownAgentError


class TestListAgents:
    """Tests for list_agents function."""

    def test_list_agents_returns_available(self) -> None:
        """list_agents returns available agent names."""
        agents = list_agents()
        assert "claude" in agents

    def test_list_agents_returns_list(self) -> None:
        """list_agents returns a list."""
        agents = list_agents()
        assert isinstance(agents, list)


class TestGetAgent:
    """Tests for get_agent function."""

    def test_get_agent_claude(self) -> None:
        """get_agent returns Claude agent."""
        agent = get_agent("claude")
        assert isinstance(agent, ClaudeAgent)

    def test_get_agent_unknown_raises_error(self) -> None:
        """get_agent raises UnknownAgentError for unknown agent."""
        with pytest.raises(UnknownAgentError) as exc_info:
            get_agent("unknown-agent")

        assert "unknown-agent" in str(exc_info.value)
        assert "claude" in str(exc_info.value)  # Shows available agents

    def test_unknown_agent_error_has_available_list(self) -> None:
        """UnknownAgentError includes list of available agents."""
        try:
            get_agent("nonexistent")
        except UnknownAgentError as e:
            assert e.name == "nonexistent"
            assert "claude" in e.available


class TestClaudeAgent:
    """Tests for Claude agent."""

    def test_claude_agent_command(self) -> None:
        """Claude agent returns correct command."""
        agent = ClaudeAgent()
        cmd = agent.get_command()
        assert cmd == ["claude", "--dangerously-skip-permissions"]

    def test_claude_agent_metadata(self) -> None:
        """Claude agent has name and description."""
        agent = ClaudeAgent()
        assert agent.name == "claude"
        assert "Claude" in agent.description

    def test_claude_agent_required_toolsets(self) -> None:
        """Claude agent requires base toolset."""
        agent = ClaudeAgent()
        toolsets = agent.get_required_toolsets()
        assert "base" in toolsets

    def test_claude_agent_required_toolsets_returns_list(self) -> None:
        """get_required_toolsets returns a list."""
        agent = ClaudeAgent()
        toolsets = agent.get_required_toolsets()
        assert isinstance(toolsets, list)
