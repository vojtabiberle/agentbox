"""Private state paths, leases and scoped deletion."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .exceptions import ConfigError


def state_home(root: Path, workspace: Path, agent: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", agent):
        raise ConfigError("Invalid agent state name")
    digest = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()[:16]
    home = root.expanduser().resolve() / digest / agent / "home"
    validate_home(home)
    return home


def validate_home(home: Path) -> None:
    """Agent-controlled symlinks must never redirect state operations."""
    for path in (home.parent.parent, home.parent, home):
        if path.is_symlink():
            raise ConfigError(f"State path must not be a symlink: {path}")


@contextmanager
def state_lease(home: Path, *, exclusive: bool = False) -> Iterator[None]:
    validate_home(home)
    home.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(home.parent / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        except BlockingIOError as err:
            raise ConfigError("State is in use by another agentbox operation") from err
        os.set_inheritable(fd, True)
        yield
    finally:
        os.close(fd)


def record_runtime(home: Path, runtime: str) -> None:
    """Remember endpoints so reset can inspect detached runs after context changes."""
    keys = (
        ("DOCKER_HOST", "DOCKER_CONTEXT")
        if runtime == "docker"
        else (
            "CONTAINER_HOST",
            "CONTAINER_CONNECTION",
        )
    )
    environment = {key: os.environ.get(key) for key in keys}
    if (
        runtime == "docker"
        and not os.environ.get("DOCKER_HOST")
        and not os.environ.get("DOCKER_CONTEXT")
    ):
        try:
            result = subprocess.run(
                ["docker", "context", "show"],
                capture_output=True,
                text=True,
                check=True,
            )
            context = result.stdout.strip()
            if not isinstance(context, str) or not context:
                raise ValueError("Missing Docker context")
            environment["DOCKER_CONTEXT"] = context
        except (OSError, subprocess.CalledProcessError, ValueError) as err:
            raise ConfigError("Cannot record Docker context") from err
    record = {"runtime": runtime, "environment": environment}
    data = json.dumps(record, sort_keys=True).encode()
    name = hashlib.sha256(data).hexdigest()[:16]
    path = home.parent / f".runtime-{name}.json"
    # Each immutable endpoint record is installed atomically; concurrent runs are safe.
    temp = home.parent / f".runtime-{name}-{os.getpid()}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def refuse_active_containers(home: Path, runtime: str) -> None:
    records = [{"runtime": runtime, "environment": {}}]
    for path in home.parent.glob(".runtime-*.json"):
        if path.is_symlink():
            raise ConfigError(f"Invalid runtime record: {path}")
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, ValueError) as err:
            raise ConfigError(f"Cannot read runtime record: {path}") from err
    for record in records:
        if not isinstance(record, dict):
            raise ConfigError("Invalid state runtime record")
        engine = record.get("runtime")
        environment = record.get("environment")
        allowed = {"DOCKER_HOST", "DOCKER_CONTEXT", "CONTAINER_HOST", "CONTAINER_CONNECTION"}
        if engine not in {"docker", "podman"} or not isinstance(environment, dict):
            raise ConfigError("Invalid state runtime record")
        env = os.environ.copy()
        for key, value in environment.items():
            if key not in allowed or (value is not None and not isinstance(value, str)):
                raise ConfigError("Invalid state runtime environment")
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        try:
            result = subprocess.run(
                [engine, "ps", "-aq"],
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            ids = result.stdout.split()
            if not ids:
                continue
            result = subprocess.run(
                [engine, "inspect", *ids],
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
            containers = json.loads(result.stdout)
            if not isinstance(containers, list):
                raise ValueError("Invalid inspect result")
            for container in containers:
                # Paused/restarting containers still own their writable state.
                status = container.get("State", {})
                if not (status.get("Running") or status.get("Paused") or status.get("Restarting")):
                    continue
                for mount in container.get("Mounts", []):
                    source = Path(mount.get("Source", "/")).resolve()
                    if source == home or source.is_relative_to(home) or home.is_relative_to(source):
                        raise ConfigError("State is mounted by an active container")
        except (
            OSError,
            subprocess.CalledProcessError,
            ValueError,
            TypeError,
            AttributeError,
        ) as err:
            raise ConfigError(
                f"Cannot verify active containers on {engine}; reset refused"
            ) from err


def reset_state(home: Path, runtime: str) -> None:
    with state_lease(home, exclusive=True):
        refuse_active_containers(home, runtime)
        validate_home(home)
        if home.exists():
            shutil.rmtree(home)


def state_size(home: Path) -> int:
    validate_home(home)
    total = 0
    for directory, _, files in os.walk(home, followlinks=False):
        for name in files:
            path = Path(directory) / name
            total += path.lstat().st_size
    return total
