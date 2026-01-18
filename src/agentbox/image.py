"""Container image building with Jinja2 templates."""

import hashlib
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader
from rich.console import Console

from .config import Config
from .container import ContainerRuntime
from .plugins import PluginManager

console = Console()


class ImageBuilder:
    """Build container images from templates."""

    def __init__(
        self,
        runtime: ContainerRuntime,
        config: Config,
        workspace: Path | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config
        self.config_path = config_path
        self.plugin_manager = PluginManager(workspace)
        self._setup_jinja()

    def _setup_jinja(self) -> None:
        """Set up Jinja2 environment."""
        # Try package resources first, fall back to filesystem
        try:
            self.env = Environment(
                loader=PackageLoader("agentbox", "templates"),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        except (TypeError, FileNotFoundError):
            # Fallback for development
            templates_dir = Path(__file__).parent / "templates"
            self.env = Environment(
                loader=FileSystemLoader(templates_dir),
                trim_blocks=True,
                lstrip_blocks=True,
            )

    def ensure_image(self, force_rebuild: bool = False) -> str:
        """Ensure the container image exists, building if necessary."""
        # Always load plugins so mounts/env are available even on cache hits
        self.plugin_manager.load(self.config.toolsets)

        # Render dockerfile first (needed for hash computation)
        dockerfile = self._render_dockerfile()

        # Compute image name (unique tag for project configs)
        image_name = self._compute_image_name(dockerfile)

        if not force_rebuild and self.runtime.image_exists(image_name):
            return image_name

        console.print(f"[cyan]Building {image_name} image...[/cyan]")
        console.print("This may take a few minutes on first run.")
        console.print()

        self.runtime.build(dockerfile, image_name)

        console.print()
        console.print("[green]Image built successfully.[/green]")

        return image_name

    def _compute_image_name(self, dockerfile: str) -> str:
        """Compute the image name, using unique tag for project configs.

        For global config or defaults: <image_name> (e.g., agentbox)
        For project config: <image_name>:<project>-<hash>
        """
        if not self._is_project_config():
            return self.config.image_name

        # Get project name from config file directory
        project_name = self._get_project_name()

        # Compute short hash of dockerfile content
        dockerfile_hash = hashlib.sha256(dockerfile.encode()).hexdigest()[:8]

        # Sanitize project name for docker tag (lowercase, alphanumeric + dash)
        safe_name = re.sub(r"[^a-z0-9-]", "-", project_name.lower())
        safe_name = re.sub(r"-+", "-", safe_name).strip("-")[:20]

        # Use config.image_name as base (respects custom image names)
        return f"{self.config.image_name}:{safe_name}-{dockerfile_hash}"

    def _is_project_config(self) -> bool:
        """Check if using a project-level config (not global).

        Project configs are .agentbox.yaml/.agentbox.yml files in cwd.
        Global configs include ~/.config/agentbox/ and ~/.agentbox.yaml.
        """
        if not self.config_path:
            return False

        config_name = self.config_path.name
        if not config_name.startswith(".agentbox."):
            return False

        # Exclude ~/.agentbox.yaml (legacy global config) by checking
        # that the config is in cwd, not in home directory
        try:
            config_parent = self.config_path.parent.resolve()
            cwd = Path.cwd().resolve()
            home = Path.home().resolve()
            return config_parent == cwd and config_parent != home
        except OSError:
            return False

    def _get_project_name(self) -> str:
        """Get the project name from config path."""
        if self.config_path:
            return self.config_path.parent.name
        return "project"

    def _render_dockerfile(self) -> str:
        """Render the Dockerfile from templates."""
        # Get dockerfile fragments from already-loaded plugins
        dockerfile_fragments = self.plugin_manager.get_dockerfile_fragments()

        template = self.env.get_template("Dockerfile.j2")
        return template.render(
            dockerfile_fragments=dockerfile_fragments,
        )
