"""Administrator-controlled, networkless batch execution (independent of project config)."""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .exceptions import ConfigError


class ServerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    image: str
    workspace_root: Path
    command: list[str] = Field(min_length=1)
    memory: str = Field(default="2g", pattern=r"^[1-9][0-9]*[mMgG]$")
    cpus: float = Field(default=1, gt=0, le=64, allow_inf_nan=False)
    pids: int = Field(default=256, ge=16, le=4096)
    timeout_seconds: int = Field(default=600, ge=1, le=86400)
    output_bytes: int = Field(default=1048576, ge=1024, le=16777216)
    tmpfs_mb: int = Field(default=128, ge=16, le=4096)
    workspace_readonly: bool = True
    broker_socket: Path | None = None
    kill_file: Path = Path("/etc/agentbox/STOP")

    @field_validator("image")
    @classmethod
    def pinned_image(cls, value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}", value):
            raise ValueError("A digest-pinned image is required")
        return value

    @field_validator("workspace_root", "broker_socket", "kill_file")
    @classmethod
    def absolute_path(cls, value: Path | None) -> Path | None:
        if value is not None and (not value.is_absolute() or ":" in str(value)):
            raise ValueError("An absolute path without ':' is required")
        return value


def trusted_file(path: Path) -> bytes:
    """Reject symlinks and paths writable by anyone except root, including ancestors."""
    if not path.is_absolute():
        raise ConfigError("Administrator configuration must use an absolute path")
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ConfigError(f"Administrator configuration is not root-controlled: {part}")
    if not path.is_file():
        raise ConfigError("Administrator configuration must be a regular file")
    return path.read_bytes()


def load_policy(path: Path) -> ServerPolicy:
    try:
        return ServerPolicy.model_validate(yaml.safe_load(trusted_file(path)))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ConfigError("Cannot load valid root-owned server policy") from error


def server_command(policy: ServerPolicy, workspace: Path, name: str) -> list[str]:
    if os.getuid() == 0:
        raise ConfigError("Server workloads require an unprivileged host user")
    root = policy.workspace_root.resolve(strict=True)
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir() or not workspace.is_relative_to(root):
        raise ConfigError("Workspace is outside the administrator-approved root")
    if ":" in str(workspace):
        raise ConfigError("Invalid workspace path")
    cmd = [
        "podman",
        "run",
        "--pull=never",
        "--name",
        name,
        "--label",
        "io.agentbox.server=true",
        "--network=none",
        "--no-hosts",
        "--read-only",
        "--read-only-tmpfs=false",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--userns=keep-id",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--ipc=private",
        "--pid=private",
        "--memory",
        policy.memory,
        "--memory-swap",
        policy.memory,
        "--cpus",
        str(policy.cpus),
        "--pids-limit",
        str(policy.pids),
        "--ulimit",
        "core=0:0",
        "--log-driver=none",
        "--http-proxy=false",
        "--workdir",
        "/workspace",
        "--env",
        "HOME=/home/agent",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "XDG_CACHE_HOME=/home/agent/.cache",
        "--volume",
        f"{workspace}:/workspace:{'ro' if policy.workspace_readonly else 'rw'},Z",
    ]
    for target in ("/home/agent", "/tmp", "/run"):
        cmd += [
            "--tmpfs",
            f"{target}:rw,nosuid,nodev,size={policy.tmpfs_mb}m,mode=1777",
        ]
    command = policy.command
    if policy.broker_socket is not None:
        socket_path = policy.broker_socket
        if not stat.S_ISSOCK(socket_path.lstat().st_mode):
            raise ConfigError("Broker endpoint must be a Unix socket")
        bridge = Path(__file__).with_name("server_bridge.py")
        cmd += [
            "--volume",
            f"{socket_path}:/run/agentbox-broker.sock:rw",
            "--volume",
            f"{bridge}:/opt/agentbox-bridge.py:ro,Z",
        ]
        command = ["python3", "/opt/agentbox-bridge.py", *command]
    # Explicit entrypoint prevents image metadata from running a different command.
    return [*cmd, "--entrypoint", command[0], "-i", policy.image, *command[1:]]


@dataclass(frozen=True)
class BatchResult:
    run_id: str
    returncode: int
    reason: str
    output: bytes


def audit(event: str, **fields: Any) -> None:
    click.echo(json.dumps({"event": event, "time": int(time.time()), **fields}), err=True)


def execute(policy: ServerPolicy, workspace: Path, data: bytes = b"") -> BatchResult:
    if len(data) > policy.output_bytes:
        raise ConfigError("Batch input exceeds policy limit")
    if policy.kill_file.exists():
        raise ConfigError("Server kill switch is active")
    run_id = uuid.uuid4().hex
    name = f"agentbox-server-{run_id}"
    command = server_command(policy, workspace, name)
    # Do not honor user-selected remote Podman endpoints or engine configuration.
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(Path.home()),
        "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
    }
    rootless = subprocess.run(
        ["podman", "info", "--format", "{{.Host.Security.Rootless}}"],
        env=env,
        capture_output=True,
        timeout=20,
        check=True,
    )
    if rootless.stdout.strip() != b"true":
        raise ConfigError("Server mode requires local rootless Podman")
    output = bytearray()
    reason = "exit"
    interrupted = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True

    old_handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    proc: subprocess.Popen[bytes] | None = None
    audit("run_started", run_id=run_id, image=policy.image)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            command,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        assert proc.stdin is not None and proc.stdout is not None
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        sent = 0
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            if data:
                selector.register(proc.stdin, selectors.EVENT_WRITE)
            else:
                proc.stdin.close()
            while selector.get_map():
                if interrupted or policy.kill_file.exists():
                    reason = "killed"
                    break
                if time.monotonic() - start >= policy.timeout_seconds:
                    reason = "timeout"
                    break
                for key, _events in selector.select(0.1):
                    if key.fileobj is proc.stdin:
                        try:
                            sent += os.write(proc.stdin.fileno(), data[sent : sent + 65536])
                        except BrokenPipeError:
                            sent = len(data)
                        if sent == len(data):
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(proc.stdout)
                        elif len(output) + len(chunk) > policy.output_bytes:
                            reason = "output_limit"
                            break
                        else:
                            output.extend(chunk)
                if reason != "exit":
                    break
            if reason == "exit":
                try:
                    proc.wait(timeout=max(0.1, policy.timeout_seconds - (time.monotonic() - start)))
                except subprocess.TimeoutExpired:
                    reason = "timeout"
    finally:
        try:
            if proc is not None:
                if proc.stdin is not None:
                    proc.stdin.close()
                if proc.stdout is not None:
                    proc.stdout.close()
                if proc.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            subprocess.run(
                ["podman", "rm", "--force", "--time", "0", "--ignore", name],
                env=env,
                capture_output=True,
                timeout=20,
            )
            remaining = subprocess.run(
                ["podman", "container", "exists", name], env=env, capture_output=True, timeout=10
            )
            if remaining.returncode != 1:
                audit("cleanup_failed", run_id=run_id, container=name)
                raise ConfigError(f"Failed to remove owned container {name}")
        finally:
            if proc is not None:
                if proc.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                if proc.stdin is not None:
                    proc.stdin.close()
                if proc.stdout is not None:
                    proc.stdout.close()
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
    code = proc.returncode if reason == "exit" else 124 if reason == "timeout" else 125
    audit(
        "run_finished",
        run_id=run_id,
        reason=reason,
        returncode=code,
        output_bytes=len(output),
        duration_seconds=round(time.monotonic() - start, 3),
    )
    return BatchResult(run_id, code, reason, bytes(output))


@click.group()
def server() -> None:
    """Run under administrator policy without loading project configuration."""


@server.command("run")
@click.argument("workspace", type=click.Path(exists=True, path_type=Path))
@click.option("--policy", type=click.Path(path_type=Path), default="/etc/agentbox/server.yaml")
@click.option("--print-output", is_flag=True, help="Explicitly emit untrusted workload output")
def server_run(workspace: Path, policy: Path, print_output: bool) -> None:
    config = load_policy(policy)
    data = sys.stdin.buffer.read(config.output_bytes + 1)
    result = execute(config, workspace, data)
    if print_output:
        sys.stdout.buffer.write(result.output)
    raise click.exceptions.Exit(result.returncode)
