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
