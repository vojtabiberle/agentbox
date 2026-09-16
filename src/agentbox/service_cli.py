"""User-facing Hermes service commands."""

import subprocess
from pathlib import Path
from typing import Literal, cast

import click

from .agents import get_agent
from .config import load_config
from .container import ContainerRuntime
from .exceptions import ConfigError
from .execution import prepare_run
from .git import detect_worktree
from .image import ImageBuilder
from .service import inspect_service, start_service, stop_service


@click.group()
@click.option("--runtime", type=click.Choice(["podman", "docker"]))
@click.pass_context
def service(ctx: click.Context, runtime: str | None) -> None:
    """Start, inspect or stop an isolated Hermes gateway."""
    ctx.ensure_object(dict)
    ctx.obj["service_runtime"] = runtime


def selected_runtime(ctx: click.Context) -> ContainerRuntime:
    name = ctx.obj["service_runtime"] or load_config()[0].runtime
    return ContainerRuntime(cast(Literal["podman", "docker"], name))


@service.command(name="start")
@click.argument(
    "workspace", type=click.Path(exists=True, file_okay=False, path_type=Path), default="."
)
@click.option("--name", required=True)
@click.option("--env", "forwarded_env", multiple=True)
@click.option(
    "--restart-policy",
    type=click.Choice(["no", "on-failure:3", "unless-stopped"]),
    default="on-failure:3",
)
@click.pass_context
def start(
    ctx: click.Context,
    workspace: Path,
    name: str,
    forwarded_env: tuple[str, ...],
    restart_policy: str,
) -> None:
    """Run configured Hermes gateway in a detached container, without published ports."""
    workspace = workspace.resolve()
    config, config_path = load_config(workspace)
    agent = get_agent("hermes")
    config = config.model_copy(
        update={"toolsets": list(dict.fromkeys(config.toolsets + ["hermes"]))}
    )
    runtime = ContainerRuntime(ctx.obj["service_runtime"] or config.runtime)
    builder = ImageBuilder(runtime, config, workspace=workspace, config_path=config_path)
    image = builder.ensure_image()
    spec = prepare_run(
        image,
        workspace,
        [],
        ["hermes", "gateway", "run", "--external-supervisor"],
        config,
        agent=agent,
        mounts=builder.plugin_manager.get_all_mounts(config.toolset_mounts, workspace),
        environment=builder.plugin_manager.get_all_environment(),
        git_worktree=detect_worktree(workspace),
        interactive=False,
        name=name,
        forwarded_env=forwarded_env,
    )
    container_id = start_service(runtime, spec, restart_policy)
    click.echo(f"Created {name}: {container_id}. Check service status/logs for gateway readiness.")


@service.command()
@click.argument("name")
@click.pass_context
def status(ctx: click.Context, name: str) -> None:
    """Show container lifecycle status without exposing environment secrets."""
    info = inspect_service(selected_runtime(ctx), name)
    state = info.get("State", {})
    click.echo(
        f"{name}: {state.get('Status', 'unknown')} (exit {state.get('ExitCode', 'unknown')})"
    )


@service.command()
@click.argument("name")
@click.option("--tail", type=click.IntRange(min=0), default=100)
@click.pass_context
def logs(ctx: click.Context, name: str, tail: int) -> None:
    """Show gateway output; log content is controlled by Hermes."""
    runtime = selected_runtime(ctx)
    info = inspect_service(runtime, name)
    try:
        subprocess.run([runtime.runtime, "logs", "--tail", str(tail), info["Id"]], check=True)
    except subprocess.CalledProcessError as err:
        raise ConfigError("Cannot read gateway logs") from err


@service.command()
@click.argument("name")
@click.pass_context
def stop(ctx: click.Context, name: str) -> None:
    """Stop/remove the managed container and retain its private HOME."""
    stop_service(selected_runtime(ctx), name)
    click.echo(f"Stopped {name}; private HOME retained")
