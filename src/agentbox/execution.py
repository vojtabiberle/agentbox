"""Resolve configuration into a container run, independent of the runtime."""

from __future__ import annotations

import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .config import Config
from .exceptions import ConfigError
from .git import GitWorktreeInfo
from .plugins.models import MountConfig
from .state import state_home

if TYPE_CHECKING:
    from .agents.base import Agent


@dataclass(frozen=True)
class Mount:
    source: Path
    target: str
    readonly: bool
    relabel: bool


@dataclass(frozen=True)
class RunSpec:
    image: str
    command: tuple[str, ...]
    mounts: tuple[Mount, ...]
    environment: tuple[tuple[str, str], ...]
    interactive: bool = True
    share_hostname: bool = False
    home: Path | None = None
    name: str | None = None
    stdin: bool = False
    forwarded_env: tuple[str, ...] = ()
    memory: str | None = None
    cpus: float | None = None
    pids_limit: int | None = None
    network: Literal["default", "none"] = "default"


def resolve_mounts(
    mounts: list[MountConfig], *, planned_sources: tuple[Path, ...] = ()
) -> tuple[Mount, ...]:
    """Normalize paths, skip optional sources and reject conflicting targets."""
    resolved: dict[str, Mount] = {}
    for mount in mounts:
        source = Path(mount.source).expanduser().resolve()
        if not source.exists() and source not in planned_sources:
            if mount.required:
                raise ConfigError(f"Required mount source does not exist: {source}")
            continue
        target = mount.target
        if target == "~" or target.startswith("~/"):
            target = str(Path.home()) + target[1:]
        target = posixpath.normpath(target)
        if target.startswith("/"):
            target = "/" + target.lstrip("/")
        if not target.startswith("/") or ":" in target or ":" in str(source):
            raise ConfigError(f"Invalid mount path: {source} -> {target}")
        item = Mount(source, target, mount.readonly, mount.relabel)
        previous = resolved.get(target)
        if previous is not None and previous != item:
            raise ConfigError(f"Conflicting mounts for {target}: {previous.source} and {source}")
        resolved[target] = item
    return tuple(resolved.values())


def prepare_run(
    image: str,
    workspace: Path,
    ro_mounts: list[Path],
    command: list[str],
    config: Config,
    *,
    mounts: list[MountConfig] | None = None,
    environment: dict[str, str] | None = None,
    agent: Agent | None = None,
    git_worktree: GitWorktreeInfo | None = None,
    interactive: bool = True,
    name: str | None = None,
    stdin: bool = False,
    forwarded_env: tuple[str, ...] = (),
    dry_run: bool = False,
) -> RunSpec:
    """Prepare private HOME and validate all mount sources before execution."""
    if name is not None and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
        raise ConfigError("Invalid container name")
    for key in forwarded_env:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", key):
            raise ConfigError(f"Invalid environment variable name: {key}")
        if key not in os.environ:
            raise ConfigError(f"Environment variable is not set: {key}")
    workspace = workspace.resolve()
    host_home = str(Path.home())
    home = state_home(config.state_dir, workspace, agent.name if agent is not None else "shell")
    try:
        if not dry_run:
            home.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as err:
        raise ConfigError(f"Cannot create container HOME {home}: {err}") from err

    requested = [
        MountConfig(source=str(workspace), target="/workspace", readonly=False, required=True),
        MountConfig(source=str(home), target=host_home, readonly=False, required=True),
        *(
            MountConfig(source=str(path), target=f"/mnt/ro{i}", required=True)
            for i, path in enumerate(ro_mounts)
        ),
    ]
    if git_worktree is not None and git_worktree.needs_mount:
        common = git_worktree.git_common_dir
        requested.append(
            MountConfig(
                source=str(common),
                target=str(common),
                readonly=False,
                required=True,
            )
        )
        if not git_worktree.git_dir.is_relative_to(common):
            requested.append(
                MountConfig(
                    source=str(git_worktree.git_dir),
                    target=str(git_worktree.git_dir),
                    readonly=False,
                    required=True,
                )
            )
    configured_mounts = [
        *(agent.get_mounts(config) if agent is not None else []),
        *(mounts or []),
        *config.mcp_mounts,
    ]
    for mount in configured_mounts:
        target = mount.target
        if target == "/home/user" or target.startswith("/home/user/"):
            target = host_home + target[len("/home/user") :]
        source = Path(mount.source).expanduser()
        if not source.is_absolute():
            source = workspace / source
        requested.append(mount.model_copy(update={"source": str(source), "target": target}))

    env = {
        "HOME": host_home,
        "PATH": f"{host_home}/.local/bin:/usr/local/bin:/usr/bin:/bin:{host_home}/.cargo/bin",
        **{
            key: value.replace("/home/user", host_home)
            for key, value in (environment or {}).items()
        },
    }
    creds = config.credentials
    if any((creds.azure, creds.aws, creds.gcloud)):
        print(
            "Warning: The 'credentials:' config section is deprecated for cloud credentials. "
            "Use cloud-aws, cloud-azure or cloud-gcloud toolsets instead.",
            file=sys.stderr,
        )
    for enabled, path in (
        (creds.github, ".config/gh"),
        (creds.azure, ".azure"),
        (creds.aws, ".aws"),
        (creds.gcloud, ".config/gcloud"),
    ):
        if enabled:
            requested.append(MountConfig(source=f"{host_home}/{path}", target=f"~/{path}"))
    ssh_sock = os.environ.get("SSH_AUTH_SOCK")
    if creds.ssh_agent and ssh_sock and Path(ssh_sock).exists():
        requested.append(
            MountConfig(
                source=ssh_sock,
                target=ssh_sock,
                readonly=False,
                relabel=False,
            )
        )
        env["SSH_AUTH_SOCK"] = ssh_sock
    return RunSpec(
        image=image,
        memory=config.limits.memory,
        cpus=config.limits.cpus,
        pids_limit=config.limits.pids_limit,
        network=config.limits.network,
        home=home,
        name=name,
        stdin=stdin,
        forwarded_env=tuple(dict.fromkeys(forwarded_env)),
        command=tuple(command),
        mounts=resolve_mounts(requested, planned_sources=(home,) if dry_run else ()),
        environment=tuple(env.items()),
        interactive=interactive,
        share_hostname=agent.share_hostname if agent is not None else False,
    )
