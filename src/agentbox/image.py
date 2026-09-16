"""Container image building with Jinja2 templates."""

import hashlib
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PackageLoader
from rich.console import Console

from .config import Config
from .container import ContainerRuntime
from .exceptions import ImageBuildError
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
        self.workspace = workspace.resolve() if workspace is not None else None
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
        """Build the toolset image and optional workspace extension."""
        extension = None
        if self.workspace is not None:
            path = self.workspace / "Dockerfile.agentbox"
            if path.exists():
                try:
                    extension = path.read_text()
                except (OSError, UnicodeError) as err:
                    raise ImageBuildError(f"Cannot read {path}: {err}") from err
                if re.search(r"(?im)^\s*FROM(?:\s|$)", extension):
                    raise ImageBuildError(f"{path}: omit FROM; agentbox supplies the base image")

        self.plugin_manager.load(self.config.toolsets)
        self.plugin_manager.get_all_mounts(self.config.toolset_mounts, self.workspace)
        dockerfile = self._render_dockerfile()
        image_name = self._compute_image_name(dockerfile)
        if force_rebuild or not self.runtime.image_exists(image_name):
            console.print(f"[cyan]Building {image_name} image...[/cyan]")
            self.runtime.build(dockerfile, image_name)
            console.print("[green]Image built successfully.[/green]")

        if extension is None:
            return image_name

        assert self.workspace is not None
        project_dockerfile = f"FROM {image_name}\n{extension}\n"
        identity = f"{self.workspace}\n{project_dockerfile}"
        digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
        project = re.sub(r"[^a-z0-9-]", "-", self.workspace.name.lower()).strip("-")[:20]
        project_image = f"{image_name.rsplit(':', 1)[0]}:{project or 'project'}-{digest}"
        console.print(f"[cyan]Building project image {project_image}...[/cyan]")
        # Let the engine evaluate COPY/ADD inputs and .dockerignore on every run.
        # Checking only image existence would reuse stale project dependencies.
        self.runtime.build(project_dockerfile, project_image, context=self.workspace)
        return project_image

    def _compute_image_name(self, dockerfile: str) -> str:
        """Compute the image name, using unique tag for project configs.

        For global config or defaults: <image_name>:<hash>
        For project config: <image_name>:<project>-<hash>
        """
        dockerfile_hash = hashlib.sha256(dockerfile.encode()).hexdigest()[:8]
        image_base = self.config.image_name
        if ":" in image_base.rsplit("/", 1)[-1]:
            image_base = image_base.rsplit(":", 1)[0]
        if not self._is_project_config():
            return f"{image_base}:{dockerfile_hash}"

        # Get project name from config file directory
        project_name = self._get_project_name()

        # Sanitize project name for docker tag (lowercase, alphanumeric + dash)
        safe_name = re.sub(r"[^a-z0-9-]", "-", project_name.lower())
        safe_name = re.sub(r"-+", "-", safe_name).strip("-")[:20]

        # Use config.image_name as base (respects custom image names)
        return f"{image_base}:{safe_name}-{dockerfile_hash}"

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
