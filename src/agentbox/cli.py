"""Command-line interface for agentbox."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .agents import get_agent
from .config import (
    Config,
    get_global_config_path,
    get_project_config_path,
    load_config,
    save_global_config,
    save_project_config,
)
from .container import ContainerRuntime
from .exceptions import AgentboxError
from .image import ImageBuilder
from .plugins import PluginManager

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
@click.option(
    "--ro",
    "-r",
    multiple=True,
    type=click.Path(exists=True),
    help="Read-only directory to mount (can be used multiple times)",
)
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

    # Build image if needed (with workspace for plugin discovery)
    builder = ImageBuilder(runtime, config, workspace=workspace_path)
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
        plugin_manager=builder.plugin_manager,
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


@main.group(name="config", invoke_without_command=True)
@click.pass_context
def config_group(ctx: click.Context) -> None:
    """Manage configuration."""
    if ctx.invoked_subcommand is None:
        # Default behavior: show config
        ctx.invoke(config_show)


@config_group.command(name="show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration."""
    cfg: Config = ctx.obj["config"]
    config_path: Path | None = ctx.obj["config_path"]

    if config_path:
        console.print(f"[cyan]Config file:[/cyan] {config_path}")
    else:
        console.print("[yellow]Config file:[/yellow] None (using defaults)")
        console.print("[dim]  Run 'agentbox config init' to create one[/dim]")

    console.print()
    console.print("[cyan]Config paths (priority order):[/cyan]")
    console.print(f"  [dim]1. Project:[/dim]  {get_project_config_path()}")
    console.print(f"  [dim]2. Global:[/dim]   {get_global_config_path()}")

    console.print()
    console.print(f"[cyan]Runtime:[/cyan]    {cfg.runtime}")
    console.print(f"[cyan]Image:[/cyan]      {cfg.image_name}")

    # Get all available toolsets
    plugin_manager = PluginManager()
    available_plugins = {p.manifest.name for p in plugin_manager.list_available()}
    enabled_toolsets = set(cfg.toolsets)

    console.print()
    console.print("[cyan]Toolsets:[/cyan]")
    for toolset in cfg.toolsets:
        if toolset in available_plugins:
            console.print(f"  [green]✓[/green] {toolset}")
        else:
            console.print(f"  [red]✗[/red] {toolset} [red](not found)[/red]")

    # Show available but inactive toolsets
    inactive = available_plugins - enabled_toolsets
    if inactive:
        console.print()
        console.print("[cyan]Available (inactive):[/cyan]")
        for toolset in sorted(inactive):
            console.print(f"  [dim]-[/dim] {toolset}")

    console.print()
    console.print("[cyan]Credentials:[/cyan]")
    console.print(f"  github:     {cfg.credentials.github}")
    console.print(f"  azure:      {cfg.credentials.azure}")
    console.print(f"  aws:        {cfg.credentials.aws}")
    console.print(f"  gcloud:     {cfg.credentials.gcloud}")
    console.print(f"  ssh_agent:  {cfg.credentials.ssh_agent}")

    if cfg.claude.global_claude_md or cfg.claude.plugins_dir:
        console.print()
        console.print("[cyan]Claude:[/cyan]")
        if cfg.claude.global_claude_md:
            console.print(f"  global_claude_md: {cfg.claude.global_claude_md}")
        if cfg.claude.plugins_dir:
            console.print(f"  plugins_dir:      {cfg.claude.plugins_dir}")


@config_group.command(name="init")
@click.option("--global", "is_global", is_flag=True, help="Create global config")
@click.option("--project", "is_project", is_flag=True, help="Create project config")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config file")
def config_init(is_global: bool, is_project: bool, force: bool) -> None:
    """Create a new configuration file."""
    # Default to global if neither specified
    if not is_global and not is_project:
        is_global = True

    if is_global:
        path = get_global_config_path()
        if path.exists() and not force:
            console.print(f"[yellow]Global config already exists:[/yellow] {path}")
            console.print("[dim]  Use --force to overwrite[/dim]")
        else:
            save_global_config()
            console.print(f"[green]Created global config:[/green] {path}")

    if is_project:
        path = get_project_config_path()
        if path.exists() and not force:
            console.print(f"[yellow]Project config already exists:[/yellow] {path}")
            console.print("[dim]  Use --force to overwrite[/dim]")
        else:
            save_project_config()
            console.print(f"[green]Created project config:[/green] {path}")


@main.command()
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True),
    help="Workspace path to include project-level plugins",
)
def toolsets(workspace: str | None) -> None:
    """List available toolsets/plugins."""
    workspace_path = Path(workspace).resolve() if workspace else None
    plugin_manager = PluginManager(workspace_path)

    plugins = plugin_manager.list_available()

    if not plugins:
        console.print("[yellow]No toolsets found.[/yellow]")
        return

    # Create table
    table = Table(title="Available Toolsets")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Origin", style="dim")
    table.add_column("Priority", justify="right", style="dim")

    # Sort by priority, then name
    plugins_sorted = sorted(plugins, key=lambda p: (p.manifest.priority, p.manifest.name))

    for plugin in plugins_sorted:
        deps = ""
        if plugin.manifest.depends_on:
            deps = f" (requires: {', '.join(plugin.manifest.depends_on)})"

        table.add_row(
            plugin.manifest.name,
            plugin.manifest.description + deps,
            plugin.origin,
            str(plugin.manifest.priority),
        )

    console.print(table)

    console.print()
    console.print("[dim]Plugin discovery paths:[/dim]")
    console.print("[dim]  1. Built-in: src/agentbox/plugins/builtin/[/dim]")
    console.print("[dim]  2. User:     ~/.config/agentbox/plugins/[/dim]")
    if workspace_path:
        console.print(f"[dim]  3. Project:  {workspace_path}/.agentbox/plugins/[/dim]")
    else:
        console.print("[dim]  3. Project:  (use --workspace to include)[/dim]")


@main.command()
@click.argument("name")
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True),
    help="Workspace path to include project-level plugins",
)
def toolset(name: str, workspace: str | None) -> None:
    """Show details of a specific toolset."""
    workspace_path = Path(workspace).resolve() if workspace else None
    plugin_manager = PluginManager(workspace_path)

    try:
        plugin = plugin_manager.get_plugin(name)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from None

    manifest = plugin.manifest

    console.print()
    console.print(f"[cyan bold]{manifest.name}[/cyan bold]")
    if manifest.description:
        console.print(f"  {manifest.description}")

    console.print()
    console.print(f"[cyan]Origin:[/cyan]   {plugin.origin}")
    console.print(f"[cyan]Priority:[/cyan] {manifest.priority}")
    console.print(f"[cyan]Path:[/cyan]     {plugin.source_path}")

    if manifest.depends_on:
        console.print()
        console.print("[cyan]Dependencies:[/cyan]")
        for dep in manifest.depends_on:
            console.print(f"  - {dep}")

    if manifest.mounts:
        console.print()
        console.print("[cyan]Mounts:[/cyan]")
        for mount in manifest.mounts:
            ro_flag = "[dim](ro)[/dim]" if mount.readonly else "[yellow](rw)[/yellow]"
            console.print(f"  {mount.source} → {mount.target} {ro_flag}")
            if mount.description:
                console.print(f"    [dim]{mount.description}[/dim]")

    if manifest.environment:
        console.print()
        console.print("[cyan]Environment:[/cyan]")
        for key, value in manifest.environment.items():
            console.print(f"  {key}={value}")


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
        console.print(line(text, 24 + len(agent)))  # 2 + 11 + 10 + agent

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
    console.print(line(text, 44))  # 2 + 35 + 8

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
