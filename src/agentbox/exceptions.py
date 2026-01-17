"""Custom exceptions for agentbox."""


class AgentboxError(Exception):
    """Base exception for agentbox errors."""

    pass


class RuntimeNotFoundError(AgentboxError):
    """Container runtime (podman/docker) not found."""

    def __init__(self, runtime: str) -> None:
        self.runtime = runtime
        alt = "docker" if runtime == "podman" else "podman"
        super().__init__(
            f"'{runtime}' is not installed.\n\n"
            f"  Install {runtime}:  https://{runtime}.io\n"
            f"  Or switch to {alt}:  Set 'runtime: {alt}' in ~/.config/agentbox/config.yaml"
        )


class ImageBuildError(AgentboxError):
    """Failed to build container image."""

    pass


class ConfigError(AgentboxError):
    """Configuration error."""

    pass


class UnknownAgentError(AgentboxError):
    """Unknown agent name specified."""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(f"Unknown agent: '{name}'. Available agents: {', '.join(available)}")


# Plugin exceptions


class PluginError(AgentboxError):
    """Base exception for plugin-related errors."""

    pass


class PluginNotFoundError(PluginError):
    """Requested plugin/toolset not found."""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        available_str = ", ".join(sorted(available)) if available else "(none)"
        super().__init__(f"Toolset '{name}' not found.\nAvailable toolsets: {available_str}")


class PluginValidationError(PluginError):
    """Plugin manifest validation failed."""

    pass


class PluginDependencyError(PluginError):
    """Plugin dependency resolution failed."""

    def __init__(self, plugin: str, missing_dep: str) -> None:
        self.plugin = plugin
        self.missing_dep = missing_dep
        super().__init__(f"Toolset '{plugin}' depends on '{missing_dep}', which is not available.")
