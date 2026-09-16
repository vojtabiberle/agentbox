"""Lifecycle for explicitly managed Hermes gateway containers."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from .container import ContainerRuntime
from .exceptions import ConfigError
from .execution import RunSpec
from .state import record_runtime, refuse_active_containers, state_lease

LABEL = "io.agentbox.service"


def validate_name(name: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
        raise ConfigError("Invalid service name")


def start_service(runtime: ContainerRuntime, spec: RunSpec, restart: str = "on-failure:3") -> str:
    if spec.name is None or spec.home is None:
        raise ConfigError("A service needs a name and private HOME")
    validate_name(spec.name)
    if restart not in {"no", "on-failure:3", "unless-stopped"}:
        raise ConfigError("Invalid restart policy")
    with state_lease(spec.home, exclusive=True):
        refuse_active_containers(spec.home, runtime.runtime)
        record_runtime(spec.home, runtime.runtime)
        cmd = runtime.build_command(spec)
        cmd.remove("--rm")
        cmd[2:2] = ["--detach", "--restart", restart, "--label", f"{LABEL}=hermes"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as err:
            raise ConfigError(f"Cannot start gateway: {err.stderr}") from err
    return result.stdout.strip()


def inspect_service(runtime: ContainerRuntime, name: str) -> dict[str, Any]:
    validate_name(name)
    try:
        result = subprocess.run(
            [runtime.runtime, "inspect", "--type", "container", name],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ValueError("Invalid inspect data")
        info: dict[str, Any] = data[0]
        if info.get("Config", {}).get("Labels", {}).get(LABEL) != "hermes":
            raise ConfigError(f"Container {name} is not an agentbox gateway")
        return info
    except (subprocess.CalledProcessError, ValueError, TypeError, AttributeError) as err:
        raise ConfigError(f"Cannot inspect gateway {name}") from err


def stop_service(runtime: ContainerRuntime, name: str) -> None:
    info = inspect_service(runtime, name)
    try:
        # Use the inspected immutable ID; never operate on a replacement with the same name.
        subprocess.run([runtime.runtime, "stop", info["Id"]], check=True, capture_output=True)
        subprocess.run([runtime.runtime, "rm", info["Id"]], check=True, capture_output=True)
    except subprocess.CalledProcessError as err:
        raise ConfigError(f"Cannot stop/remove gateway {name}") from err
