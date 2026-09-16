"""Base agent interface."""

from abc import ABC, abstractmethod

from ..config import Config
from ..plugins.models import MountConfig


class Agent(ABC):
    """Base class for all agents."""

    name: str
    description: str

    @abstractmethod
    def get_command(self) -> list[str]:
        """Return the command to run this agent."""
        ...

    def get_required_toolsets(self) -> list[str]:
        """Return toolsets required by this agent."""
        return []

    def get_mounts(self, config: Config) -> list[MountConfig]:
        """Explicit host files shared with this agent."""
        return []
