"""Tests for agentbox exceptions."""

import pytest

from agentbox.exceptions import (
    AgentboxError,
    ConfigError,
    ImageBuildError,
    PluginDependencyError,
    PluginError,
    PluginNotFoundError,
    PluginValidationError,
    RuntimeNotFoundError,
    UnknownAgentError,
)


class TestAgentboxError:
    """Tests for base AgentboxError."""

    def test_is_exception(self) -> None:
        """AgentboxError is an Exception."""
        assert issubclass(AgentboxError, Exception)

    def test_can_be_raised(self) -> None:
        """AgentboxError can be raised and caught."""
        with pytest.raises(AgentboxError):
            raise AgentboxError("test error")

    def test_message_preserved(self) -> None:
        """AgentboxError preserves message."""
        error = AgentboxError("test message")
        assert str(error) == "test message"


class TestRuntimeNotFoundError:
    """Tests for RuntimeNotFoundError."""

    def test_is_agentbox_error(self) -> None:
        """RuntimeNotFoundError is an AgentboxError."""
        assert issubclass(RuntimeNotFoundError, AgentboxError)

    def test_includes_runtime_name(self) -> None:
        """RuntimeNotFoundError includes runtime name in message."""
        error = RuntimeNotFoundError("podman")
        assert "podman" in str(error)

    def test_includes_install_suggestion(self) -> None:
        """RuntimeNotFoundError includes install suggestion."""
        error = RuntimeNotFoundError("podman")
        assert "Install" in str(error) or "install" in str(error)

    def test_includes_alternative(self) -> None:
        """RuntimeNotFoundError suggests alternative runtime."""
        error = RuntimeNotFoundError("podman")
        assert "docker" in str(error)

        error = RuntimeNotFoundError("docker")
        assert "podman" in str(error)

    def test_stores_runtime_attribute(self) -> None:
        """RuntimeNotFoundError stores runtime as attribute."""
        error = RuntimeNotFoundError("podman")
        assert error.runtime == "podman"


class TestImageBuildError:
    """Tests for ImageBuildError."""

    def test_is_agentbox_error(self) -> None:
        """ImageBuildError is an AgentboxError."""
        assert issubclass(ImageBuildError, AgentboxError)


class TestConfigError:
    """Tests for ConfigError."""

    def test_is_agentbox_error(self) -> None:
        """ConfigError is an AgentboxError."""
        assert issubclass(ConfigError, AgentboxError)


class TestUnknownAgentError:
    """Tests for UnknownAgentError."""

    def test_is_agentbox_error(self) -> None:
        """UnknownAgentError is an AgentboxError."""
        assert issubclass(UnknownAgentError, AgentboxError)

    def test_includes_agent_name(self) -> None:
        """UnknownAgentError includes agent name in message."""
        error = UnknownAgentError("badagent", ["claude", "other"])
        assert "badagent" in str(error)

    def test_includes_available_agents(self) -> None:
        """UnknownAgentError includes available agents in message."""
        error = UnknownAgentError("badagent", ["claude", "other"])
        assert "claude" in str(error)
        assert "other" in str(error)

    def test_stores_attributes(self) -> None:
        """UnknownAgentError stores name and available as attributes."""
        error = UnknownAgentError("badagent", ["claude"])
        assert error.name == "badagent"
        assert error.available == ["claude"]


class TestPluginError:
    """Tests for base PluginError."""

    def test_is_agentbox_error(self) -> None:
        """PluginError is an AgentboxError."""
        assert issubclass(PluginError, AgentboxError)

    def test_can_be_raised(self) -> None:
        """PluginError can be raised and caught."""
        with pytest.raises(PluginError):
            raise PluginError("plugin error")

    def test_can_catch_as_agentbox_error(self) -> None:
        """PluginError can be caught as AgentboxError."""
        with pytest.raises(AgentboxError):
            raise PluginError("plugin error")


class TestPluginNotFoundError:
    """Tests for PluginNotFoundError."""

    def test_is_plugin_error(self) -> None:
        """PluginNotFoundError is a PluginError."""
        assert issubclass(PluginNotFoundError, PluginError)

    def test_is_agentbox_error(self) -> None:
        """PluginNotFoundError is an AgentboxError."""
        assert issubclass(PluginNotFoundError, AgentboxError)

    def test_includes_plugin_name(self) -> None:
        """PluginNotFoundError includes plugin name in message."""
        error = PluginNotFoundError("missing-plugin", ["base", "python"])
        assert "missing-plugin" in str(error)

    def test_includes_available_plugins(self) -> None:
        """PluginNotFoundError includes available plugins in message."""
        error = PluginNotFoundError("missing", ["base", "python", "go"])
        assert "base" in str(error)
        assert "python" in str(error)
        assert "go" in str(error)

    def test_handles_empty_available(self) -> None:
        """PluginNotFoundError handles empty available list."""
        error = PluginNotFoundError("missing", [])
        assert "(none)" in str(error)

    def test_sorts_available_plugins(self) -> None:
        """PluginNotFoundError sorts available plugins."""
        error = PluginNotFoundError("missing", ["zoo", "apple", "mango"])
        msg = str(error)
        # Should appear sorted: apple, mango, zoo
        assert msg.index("apple") < msg.index("mango") < msg.index("zoo")

    def test_stores_attributes(self) -> None:
        """PluginNotFoundError stores name and available as attributes."""
        error = PluginNotFoundError("missing", ["base"])
        assert error.name == "missing"
        assert error.available == ["base"]


class TestPluginValidationError:
    """Tests for PluginValidationError."""

    def test_is_plugin_error(self) -> None:
        """PluginValidationError is a PluginError."""
        assert issubclass(PluginValidationError, PluginError)

    def test_is_agentbox_error(self) -> None:
        """PluginValidationError is an AgentboxError."""
        assert issubclass(PluginValidationError, AgentboxError)

    def test_preserves_message(self) -> None:
        """PluginValidationError preserves message."""
        error = PluginValidationError("Invalid YAML in file.yaml")
        assert "Invalid YAML" in str(error)


class TestPluginDependencyError:
    """Tests for PluginDependencyError."""

    def test_is_plugin_error(self) -> None:
        """PluginDependencyError is a PluginError."""
        assert issubclass(PluginDependencyError, PluginError)

    def test_is_agentbox_error(self) -> None:
        """PluginDependencyError is an AgentboxError."""
        assert issubclass(PluginDependencyError, AgentboxError)

    def test_includes_plugin_name(self) -> None:
        """PluginDependencyError includes plugin name in message."""
        error = PluginDependencyError("my-plugin", "missing-dep")
        assert "my-plugin" in str(error)

    def test_includes_missing_dependency(self) -> None:
        """PluginDependencyError includes missing dependency in message."""
        error = PluginDependencyError("my-plugin", "missing-dep")
        assert "missing-dep" in str(error)

    def test_stores_attributes(self) -> None:
        """PluginDependencyError stores plugin and missing_dep as attributes."""
        error = PluginDependencyError("my-plugin", "missing-dep")
        assert error.plugin == "my-plugin"
        assert error.missing_dep == "missing-dep"


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_all_errors_are_agentbox_errors(self) -> None:
        """All custom exceptions inherit from AgentboxError."""
        exceptions = [
            RuntimeNotFoundError,
            ImageBuildError,
            ConfigError,
            UnknownAgentError,
            PluginError,
            PluginNotFoundError,
            PluginValidationError,
            PluginDependencyError,
        ]
        for exc in exceptions:
            assert issubclass(exc, AgentboxError)

    def test_plugin_errors_are_plugin_errors(self) -> None:
        """All plugin exceptions inherit from PluginError."""
        plugin_exceptions = [
            PluginNotFoundError,
            PluginValidationError,
            PluginDependencyError,
        ]
        for exc in plugin_exceptions:
            assert issubclass(exc, PluginError)

    def test_catch_all_plugin_errors(self) -> None:
        """Can catch all plugin errors with PluginError."""
        errors = [
            PluginNotFoundError("test", []),
            PluginValidationError("test"),
            PluginDependencyError("test", "dep"),
        ]
        for error in errors:
            with pytest.raises(PluginError):
                raise error

    def test_catch_all_with_agentbox_error(self) -> None:
        """Can catch all errors with AgentboxError."""
        errors = [
            RuntimeNotFoundError("podman"),
            ImageBuildError("build failed"),
            ConfigError("bad config"),
            UnknownAgentError("bad", []),
            PluginNotFoundError("test", []),
            PluginValidationError("test"),
            PluginDependencyError("test", "dep"),
        ]
        for error in errors:
            with pytest.raises(AgentboxError):
                raise error
