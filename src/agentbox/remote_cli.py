"""`agentbox remote`: run tasks and services on an SSH host."""

from __future__ import annotations

import sys

import click

from . import __version__
from .remote_registry import RemoteHost, get_host, load_registry, validate_remote_name
from .remote_services import (
    RESTART_POLICIES,
    service_logs,
    service_status,
    setup_service,
    start_service,
    stop_service,
)
from .remote_setup import StepResult, local_wheel, run_doctor, run_setup
from .remote_ssh import RemoteShell
from .remote_tasks import attach_task, list_tasks, start_task, stop_task, task_logs


class ClickPrompter:
    def ask(self, text: str, default: str | None = None) -> str:
        return str(click.prompt(text, default=default))

    def confirm(self, text: str) -> bool:
        return click.confirm(text, default=False)


def make_shell(host: RemoteHost) -> RemoteShell:
    return RemoteShell(host.ssh)


def _report(results: list[StepResult]) -> None:
    for result in results:
        click.echo(f"{result.status.upper():6} {result.name}: {result.detail}")
    if any(result.status == "action" for result in results):
        sys.exit(1)


@click.group()
def remote() -> None:
    """Run agent tasks and services on an SSH host."""


@remote.command()
@click.argument("host")
@click.option("--ssh", "ssh_destination", help="ssh destination; defaults to HOST for a new remote")
@click.option(
    "--reinstall",
    is_flag=True,
    help="Reinstall agentbox on the remote even if the version matches (source checkouts)",
)
def setup(host: str, ssh_destination: str | None, reinstall: bool) -> None:
    """Prepare and validate a remote host (re-runnable)."""
    validate_remote_name(host)
    existing = load_registry().get(host)
    destination = ssh_destination or (existing.ssh if existing else host)
    results = run_setup(
        host,
        RemoteShell(destination),
        ClickPrompter(),
        local_version=__version__,
        wheel_builder=local_wheel,
        force_reinstall=reinstall,
    )
    _report(results)


@remote.command()
@click.argument("host")
def doctor(host: str) -> None:
    """Validate a remote host without changing anything."""
    remote_host = get_host(host)
    _report(run_doctor(remote_host, make_shell(remote_host), local_version=__version__))


@remote.command(name="run")
@click.argument("host")
@click.option("--name", "task", required=True)
@click.option("--branch", required=True)
@click.option("--agent")
@click.argument("agent_args", nargs=-1, type=click.UNPROCESSED)
def run_task(
    host: str, task: str, branch: str, agent: str | None, agent_args: tuple[str, ...]
) -> None:
    """Start a task from BRANCH in its own worktree and tmux session."""
    remote_host = get_host(host)
    start_task(
        make_shell(remote_host), remote_host, task, branch, agent or remote_host.agent, agent_args
    )
    click.echo(f"Started {task}. Attach: agentbox remote attach {host} {task}")


@remote.command(name="list")
@click.argument("host")
def list_command(host: str) -> None:
    """List tasks and their state (running, exited, stopped)."""
    remote_host = get_host(host)
    tasks = list_tasks(make_shell(remote_host), remote_host)
    if not tasks:
        click.echo(f"No tasks on {host}")
    for status in tasks:
        click.echo(f"{status.name}\t{status.state}")


@remote.command()
@click.argument("host")
@click.argument("task")
def attach(host: str, task: str) -> None:
    """Attach to a task's tmux session (detach with Ctrl+b d)."""
    remote_host = get_host(host)
    sys.exit(attach_task(make_shell(remote_host), remote_host, task))


@remote.command()
@click.argument("host")
@click.argument("task")
@click.option("--tail", type=click.IntRange(min=1), default=200)
def logs(host: str, task: str, tail: int) -> None:
    """Print recent task output."""
    remote_host = get_host(host)
    click.echo(task_logs(make_shell(remote_host), remote_host, task, tail), nl=False)


@remote.command()
@click.argument("host")
@click.argument("task")
@click.option("--remove-worktree", is_flag=True)
@click.option(
    "--discard-ignored",
    is_flag=True,
    help="With --remove-worktree, also delete Git-ignored files in the worktree",
)
def stop(host: str, task: str, remove_worktree: bool, discard_ignored: bool) -> None:
    """Stop a task; keeps its worktree unless --remove-worktree."""
    remote_host = get_host(host)
    stop_task(
        make_shell(remote_host),
        remote_host,
        task,
        remove_worktree=remove_worktree,
        discard_ignored=discard_ignored,
    )
    click.echo(f"Stopped {task}")


@remote.group()
def service() -> None:
    """Manage Hermes gateway services on a remote host."""


@service.command(name="setup")
@click.argument("host")
def service_setup(host: str) -> None:
    """Interactive Hermes gateway setup on the remote."""
    remote_host = get_host(host)
    sys.exit(setup_service(make_shell(remote_host), remote_host))


@service.command(name="start")
@click.argument("host")
@click.argument("name")
@click.option("--restart-policy", type=click.Choice(RESTART_POLICIES), default="on-failure:3")
@click.option(
    "--env", "forwarded_env", multiple=True, help="Remote environment variable name to forward"
)
def service_start(
    host: str, name: str, restart_policy: str, forwarded_env: tuple[str, ...]
) -> None:
    """Start a Hermes gateway service."""
    remote_host = get_host(host)
    click.echo(
        start_service(make_shell(remote_host), remote_host, name, restart_policy, forwarded_env),
        nl=False,
    )


@service.command(name="status")
@click.argument("host")
@click.argument("name")
def service_status_command(host: str, name: str) -> None:
    """Show service status."""
    remote_host = get_host(host)
    click.echo(service_status(make_shell(remote_host), remote_host, name), nl=False)


@service.command(name="logs")
@click.argument("host")
@click.argument("name")
@click.option("--tail", type=click.IntRange(min=0), default=100)
def service_logs_command(host: str, name: str, tail: int) -> None:
    """Show service logs."""
    remote_host = get_host(host)
    click.echo(service_logs(make_shell(remote_host), remote_host, name, tail), nl=False)


@service.command(name="stop")
@click.argument("host")
@click.argument("name")
def service_stop(host: str, name: str) -> None:
    """Stop a service."""
    remote_host = get_host(host)
    click.echo(stop_service(make_shell(remote_host), remote_host, name), nl=False)
