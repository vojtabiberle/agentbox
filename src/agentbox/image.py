"""Container image building with Jinja2 templates."""

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
    ) -> None:
        self.runtime = runtime
        self.config = config
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
        image_name = self.config.image_name

        # Always load plugins so mounts/env are available even on cache hits
        self.plugin_manager.load(self.config.toolsets)

        if not force_rebuild and self.runtime.image_exists(image_name):
            return image_name

        console.print(f"[cyan]Building {image_name} image...[/cyan]")
        console.print("This may take a few minutes on first run.")
        console.print()

        dockerfile = self._render_dockerfile()
        self.runtime.build(dockerfile, image_name)

        console.print()
        console.print("[green]Image built successfully.[/green]")

        return image_name

    def _render_dockerfile(self) -> str:
        """Render the Dockerfile from templates."""
        # Get dockerfile fragments from already-loaded plugins
        dockerfile_fragments = self.plugin_manager.get_dockerfile_fragments()

        template = self.env.get_template("Dockerfile.j2")
        return template.render(
            dockerfile_fragments=dockerfile_fragments,
        )
