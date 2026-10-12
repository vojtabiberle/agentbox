"""Laptop-side registry of remote task hosts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from .config import CONFIG_ENV
from .exceptions import ConfigError, RemoteError

_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")
CONFIG_FILE = "agentbox.yaml"


class RemoteHost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ssh: str
    repository: str
    base_dir: str
    agent: str
    runtime: Literal["podman", "docker"]

    @field_validator("ssh", "repository", "agent")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("base_dir")
    @classmethod
    def _absolute(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("base_dir must be an absolute path on the remote")
        return value.rstrip("/")

    @property
    def repo_dir(self) -> str:
        return f"{self.base_dir}/repo"

    @property
    def worktrees_dir(self) -> str:
        return f"{self.base_dir}/wt"

    @property
    def config_file(self) -> str:
        return f"{self.base_dir}/{CONFIG_FILE}"

    def agentbox(self, *args: str) -> list[str]:
        # Remote-task settings stay out of the remote user's global config.
        return ["env", f"{CONFIG_ENV}={self.config_file}", "agentbox", *args]


def validate_remote_name(name: str) -> None:
    if not _NAME.fullmatch(name):
        raise ConfigError(f"Invalid remote name: {name}")


def registry_path() -> Path:
    return Path.home() / ".config" / "agentbox" / "remotes.yaml"


def load_registry(path: Path | None = None) -> dict[str, RemoteHost]:
    path = path or registry_path()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    if data is not None and not isinstance(data, dict):
        raise ConfigError(f"Invalid remote registry {path}: expected a mapping")
    data = data or {}
    remotes = data.get("remotes")
    if remotes is not None and not isinstance(remotes, dict):
        raise ConfigError(f"Invalid remote registry {path}: 'remotes' must be a mapping")
    hosts: dict[str, RemoteHost] = {}
    for name, values in (remotes or {}).items():
        try:
            hosts[name] = RemoteHost.model_validate(values)
        except ValidationError as err:
            raise ConfigError(f"Invalid remote '{name}' in {path}: {err}") from None
    return hosts


def get_host(name: str, path: Path | None = None) -> RemoteHost:
    hosts = load_registry(path)
    if name not in hosts:
        raise RemoteError(f"Unknown remote '{name}'. Run: agentbox remote setup {name}")
    return hosts[name]


def save_host(name: str, host: RemoteHost, path: Path | None = None) -> Path:
    validate_remote_name(name)
    path = path or registry_path()
    hosts = load_registry(path)
    hosts[name] = host
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"remotes": {key: value.model_dump() for key, value in sorted(hosts.items())}}
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path
