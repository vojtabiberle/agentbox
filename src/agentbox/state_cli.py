"""Commands for inspecting and resetting private state."""

from pathlib import Path

import click

from .agents import get_agent
from .config import load_config
from .state import reset_state, state_home, state_size


@click.group()
def state() -> None:
    """Inspect private HOME or reset one workspace/agent."""


@state.command(name="show")
@click.argument("workspace", type=click.Path(path_type=Path), default=".")
@click.option("--agent", default="claude")
@click.option("--path-only", is_flag=True)
def show(workspace: Path, agent: str, path_only: bool) -> None:
    """Show private HOME location and byte usage; never print its contents."""
    get_agent(agent)
    config, _ = load_config(workspace.resolve())
    home = state_home(config.state_dir, workspace, agent, config.state_scope)
    click.echo(
        str(home)
        if path_only
        else f"{home}\nScope: {config.state_scope}\nBytes: {state_size(home)}"
    )


@state.command(name="list")
@click.option("--workspace", type=click.Path(path_type=Path), default=".")
def list_states(workspace: Path) -> None:
    """List workspace hashes, agents, HOME paths and byte usage."""
    config, _ = load_config(workspace.resolve())
    root = config.state_dir.expanduser().resolve()
    for home in sorted(root.glob("*/*/home")):
        click.echo(f"{home.parent.parent.name}\t{home.parent.name}\t{state_size(home)}\t{home}")


@state.command(name="reset")
@click.argument("workspace", type=click.Path(path_type=Path), default=".")
@click.option("--agent", default="claude")
@click.option("--yes", is_flag=True, help="Explicitly confirm deletion without a prompt")
def reset(workspace: Path, agent: str, yes: bool) -> None:
    """Delete only this workspace/agent HOME after checking active containers.

    With state_scope: repository this is the HOME shared by all worktrees of the repository.
    """
    get_agent(agent)
    config, _ = load_config(workspace.resolve())
    home = state_home(config.state_dir, workspace, agent, config.state_scope)
    if not yes and not click.confirm(
        f"Delete private HOME and all credentials/sessions in {home}?"
    ):
        raise click.Abort()
    reset_state(home, config.runtime)
    click.echo(f"Reset: {home}")
