"""Command-line interface for agentbox."""

import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .agents import get_agent
from .config import Config, load_config
from .container import ContainerRuntime
from .exceptions import AgentboxError
from .image import ImageBuilder

console = Console(stderr=True)


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="agentbox")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Run AI coding agents in isolated containers."""
    ctx.ensure_object(dict)
    config, config_path = load_config()
    ctx.obj["config"] = config
    ctx.obj["config_path"] = config_path

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.argument("workspace", type=click.Path(), default=".")
@click.option("--bash", is_flag=True, help="Run bash instead of agent (for debugging)")
@click.option("--agent", "-a", default="claude", help="Agent to run (default: claude)")
@click.option("--ro", "-r", multiple=True, type=click.Path(exists=True),
              help="Read-only directory to mount (can be used multiple times)")
@click.option("--rebuild", is_flag=True, help="Force rebuild the container image")
@click.pass_context
def run(
    ctx: click.Context,
    workspace: str,
    bash: bool,
    agent: str,
    ro: tuple[str, ...],
    rebuild: bool,
) -> None:
    """Run an agent in an isolated container.

    WORKSPACE is the directory to mount read-write (default: current directory).
    """
    config: Config = ctx.obj["config"]
    workspace_path = Path(workspace).resolve()

    # Create workspace if it doesn't exist
    if not workspace_path.exists():
        if not click.confirm(f"Directory doesn't exist. Create it?\n  {workspace_path}"):
            raise SystemExit(1)
        workspace_path.mkdir(parents=True)
        console.print(f"[green]Created:[/green] {workspace_path}")

    # Initialize container runtime
    runtime = ContainerRuntime(config.runtime)

    # Build image if needed
    builder = ImageBuilder(runtime, config)
    image_name = builder.ensure_image(force_rebuild=rebuild)

    # Get agent configuration
    agent_instance = get_agent(agent)

    # Prepare read-only mounts
    ro_mounts = [Path(p).resolve() for p in ro]

    # Print banner
    _print_banner(workspace_path, ro_mounts, bash, agent)

    # Run container
    if bash:
        cmd = ["bash"]
    else:
        cmd = agent_instance.get_command()

    runtime.run(
        image=image_name,
        workspace=workspace_path,
        ro_mounts=ro_mounts,
        command=cmd,
        config=config,
    )


@main.command()
@click.option("--rebuild", is_flag=True, help="Force rebuild even if image exists")
@click.pass_context
def build(ctx: click.Context, rebuild: bool) -> None:
    """Build the container image."""
    config: Config = ctx.obj["config"]
    runtime = ContainerRuntime(config.runtime)
    builder = ImageBuilder(runtime, config)

    image_name = builder.ensure_image(force_rebuild=rebuild)
    console.print(f"[green]Image ready:[/green] {image_name}")


@main.command(name="config")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Show current configuration."""
    cfg: Config = ctx.obj["config"]
    config_path: Path | None = ctx.obj["config_path"]

    if config_path:
        console.print(f"[cyan]Config file:[/cyan] {config_path}")
    else:
        console.print("[yellow]Config file:[/yellow] None (using defaults)")
        console.print(f"[dim]  Create config at: ~/.config/agentbox/config.yaml[/dim]")

    console.print()
    console.print(f"[cyan]Runtime:[/cyan]    {cfg.runtime}")
    console.print(f"[cyan]Image:[/cyan]      {cfg.image_name}")
    console.print(f"[cyan]Toolsets:[/cyan]   {', '.join(cfg.toolsets)}")

    console.print()
    console.print("[cyan]Credentials:[/cyan]")
    console.print(f"  github:  {cfg.credentials.github}")
    console.print(f"  azure:   {cfg.credentials.azure}")
    console.print(f"  aws:     {cfg.credentials.aws}")
    console.print(f"  gcloud:  {cfg.credentials.gcloud}")

    if cfg.claude.global_claude_md or cfg.claude.plugins_dir:
        console.print()
        console.print("[cyan]Claude:[/cyan]")
        if cfg.claude.global_claude_md:
            console.print(f"  global_claude_md: {cfg.claude.global_claude_md}")
        if cfg.claude.plugins_dir:
            console.print(f"  plugins_dir:      {cfg.claude.plugins_dir}")


def _print_banner(
    workspace: Path,
    ro_mounts: list[Path],
    bash_mode: bool,
    agent: str,
) -> None:
    """Print the danger zone banner."""
    W = 60  # inner width

    def line(content: str, visible_len: int) -> str:
        """Create a bordered line with proper padding."""
        padding = W - visible_len
        return f"[red]║[/red]{content}{' ' * padding}[red]║[/red]"

    console.print()
    console.print("[red]╔" + "═" * W + "╗[/red]")

    if bash_mode:
        text = "  [yellow]DEBUG MODE[/yellow] - Running bash shell"
        console.print(line(text, 31))  # 2 + 10 + 10 + 9 = 31
    else:
        text = f"  [yellow]DANGER ZONE[/yellow] - Running {agent}"
        console.print(line(text, 23 + len(agent)))  # 2 + 11 + 10 + agent

    text = "  [cyan]Read-Write:[/cyan]"
    console.print(line(text, 13))  # 2 + 11

    ws_str = str(workspace)[:56]
    console.print(line(f"    {ws_str}", 4 + len(ws_str)))

    if ro_mounts:
        text = "  [dim]Read-Only:[/dim]"
        console.print(line(text, 12))  # 2 + 10
        for mount in ro_mounts:
            m_str = str(mount)[:56]
            console.print(line(f"    [dim]{m_str}[/dim]", 4 + len(m_str)))

    console.print(line("", 0))
    text = "  Everything else on your system is [green]isolated[/green]"
    console.print(line(text, 45))  # 2 + 35 + 8

    console.print("[red]╚" + "═" * W + "╝[/red]")
    console.print()


def cli() -> None:
    """Entry point with error handling."""
    try:
        main(standalone_mode=False)
    except click.exceptions.Abort:
        # User cancelled (Ctrl+C or answered 'no' to prompt)
        console.print("\nAborted.")
        sys.exit(1)
    except click.ClickException as e:
        # Click's own errors (bad arguments, etc.)
        e.show()
        sys.exit(e.exit_code)
    except AgentboxError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
