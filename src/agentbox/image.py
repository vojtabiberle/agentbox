"""Container image building with Jinja2 templates."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader
from rich.console import Console

from .config import Config
from .container import ContainerRuntime

console = Console()


class ImageBuilder:
    """Build container images from templates."""

    def __init__(self, runtime: ContainerRuntime, config: Config) -> None:
        self.runtime = runtime
        self.config = config
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
        template = self.env.get_template("Dockerfile.j2")
        return template.render(
            toolsets=self.config.toolsets,
        )
