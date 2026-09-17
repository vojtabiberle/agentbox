"""Read-only run descriptions and environment diagnostics."""

import json
import os
import subprocess
from pathlib import Path

import click

from .agents import get_agent
from .config import Config, load_config
from .container import ContainerRuntime
from .exceptions import AgentboxError
from .execution import RunSpec, prepare_run
from .git import detect_worktree
from .image import ImageBuilder


def describe_run(spec: RunSpec, config: Config, workspace: Path) -> None:
    """Describe effective access without command arguments or environment values."""
    extension = config.project_dockerfile or Path("Dockerfile.agentbox")
    click.echo(
        json.dumps(
            {
                "runtime": config.runtime,
                "limits": config.limits.model_dump(),
                "base_image": spec.image,
                "project_dockerfile": str(extension) if (workspace / extension).is_file() else None,
                "image_note": "Base image only; project extensions require a build.",
                "workspace": str(workspace),
                "home": str(spec.home),
                "name": spec.name,
                "executable": spec.command[0],
                "argument_count": len(spec.command) - 1,
                "interactive": spec.interactive,
                "stdin": spec.stdin,
                "share_hostname": spec.share_hostname,
                "mounts": [
                    {
                        "source": str(m.source),
                        "target": m.target,
                        "readonly": m.readonly,
                        "relabel": m.relabel,
                    }
                    for m in spec.mounts
                ],
                "environment_names": sorted(set(dict(spec.environment)) | set(spec.forwarded_env)),
            },
            indent=2,
        )
    )


@click.command()
@click.argument(
    "workspace", type=click.Path(exists=True, file_okay=False, path_type=Path), default="."
)
@click.option("--agent", default="claude")
def doctor(workspace: Path, agent: str) -> None:
    """Check configuration, runtime, access and cached agent startup prerequisites."""
    workspace = workspace.resolve()
    try:
        config, config_path = load_config(workspace)
    except AgentboxError as err:
        raise click.ClickException(
            "Configuration cannot be loaded; check YAML syntax and field types."
        ) from err
    selected = get_agent(agent)
    config = config.model_copy(
        update={"toolsets": list(dict.fromkeys(config.toolsets + selected.get_required_toolsets()))}
    )
    runtime = ContainerRuntime(config.runtime)
    try:
        subprocess.run([runtime.runtime, "info"], check=True, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as err:
        raise click.ClickException(
            "Runtime is unavailable; check the daemon, context and socket permissions."
        ) from err
    builder = ImageBuilder(runtime, config, workspace, config_path)
    image = builder.ensure_image(dry_run=True)
    spec = prepare_run(
        image,
        workspace,
        [],
        selected.get_command(),
        config,
        agent=selected,
        mounts=builder.plugin_manager.get_all_mounts(config.toolset_mounts, workspace),
        environment=builder.plugin_manager.get_all_environment(),
        git_worktree=detect_worktree(workspace),
        dry_run=True,
        interactive=False,
    )
    assert spec.home is not None
    ancestor = spec.home
    while not ancestor.exists():
        ancestor = ancestor.parent
    for path in (workspace, ancestor):
        if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK):
            raise click.ClickException(f"Directory is not writable/searchable: {path}")
    click.echo("OK: configuration, runtime connection, mounts and host directory permissions")
    if not runtime.image_exists(image):
        raise click.ClickException(
            "Base image is not cached; run agentbox build for this workspace/agent first."
        )
    try:
        result = subprocess.run(
            [
                runtime.runtime,
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--user",
                "65534:65534",
                "--entrypoint",
                "/bin/sh",
                image,
                "-c",
                'command -v "$1" >/dev/null',
                "agentbox-doctor",
                selected.get_command()[0],
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise click.ClickException(
            "Image executable check failed; check runtime image compatibility."
        ) from err
    if result.returncode:
        raise click.ClickException(
            "Selected agent is unavailable in the base image; build or select a compatible image."
        )
    click.echo("OK: selected agent executable exists in cached base image")
    click.echo("Provider authentication and project extension readiness are not checked.")
