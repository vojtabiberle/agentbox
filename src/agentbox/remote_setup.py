"""Remote host setup wizard and read-only doctor."""

from __future__ import annotations

import base64
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import yaml
from pydantic import ValidationError

from .exceptions import RemoteError
from .remote_registry import RemoteHost, load_registry, save_host
from .remote_ssh import RemoteShell

Status = Literal["ok", "fixed", "action", "info"]
WheelBuilder = Callable[[], AbstractContextManager["Path | None"]]
# Mirrors agentbox.config.get_config_paths(): a repo-tracked file always wins (it is
# checked out into every worktree), then the remote user's first existing global file.
REPO_CONFIG_NAMES = (".agentbox.yaml", ".agentbox.yml")
GLOBAL_CONFIG_CANDIDATES = (
    ".config/agentbox/config.yaml",
    ".config/agentbox/config.yml",
    ".agentbox.yaml",
)
WHEEL_DIR = ".cache/agentbox"
TOOLS = ("git", "tmux", "pipx")
_DOUBLE_QUOTE_SAFE = re.compile(r'[^"$`\\!]*')


@dataclass(frozen=True)
class StepResult:
    name: str
    status: Status
    detail: str


class Prompter(Protocol):
    def ask(self, text: str, default: str | None = None) -> str: ...

    def confirm(self, text: str) -> bool: ...


@contextmanager
def local_wheel() -> Iterator[Path | None]:
    root = Path(__file__).resolve().parents[2]
    if not (root / "pyproject.toml").exists():
        yield None
        return
    target = Path(tempfile.mkdtemp(prefix="agentbox-wheel-"))
    try:
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "-q",
                    "-w",
                    str(target),
                    str(root),
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as err:
            stderr = (err.stderr or b"").decode(errors="replace").strip()
            raise RemoteError(f"Cannot build the agentbox wheel: {stderr or err}") from None
        wheel = next(target.glob("agentbox-*.whl"), None)
        if wheel is None:
            raise RemoteError(f"pip produced no agentbox wheel in {target}")
        yield wheel
    finally:
        shutil.rmtree(target, ignore_errors=True)


def _ssh(shell: RemoteShell) -> StepResult:
    result = shell.run(["true"])
    if result.returncode != 0:
        return StepResult("ssh", "action", result.stderr.strip() or f"exit {result.returncode}")
    return StepResult("ssh", "ok", shell.destination)


def _runtime(shell: RemoteShell, expected: str | None) -> tuple[StepResult, str | None]:
    candidates = [expected] if expected else ["podman", "docker"]
    for runtime in candidates:
        if runtime and shell.run([runtime, "info"]).returncode == 0:
            return StepResult("runtime", "ok", runtime), runtime
    return (
        StepResult(
            "runtime",
            "action",
            "Install Podman (e.g. `sudo apt-get install -y podman`) or give the SSH user "
            "Docker access (`sudo usermod -aG docker $USER`, or `gpasswd -a` for OS Login "
            "users), then re-run",
        ),
        None,
    )


def _tools(shell: RemoteShell) -> StepResult:
    missing = [tool for tool in TOOLS if shell.run(["command", "-v", tool]).returncode != 0]
    if missing:
        return StepResult(
            "tools",
            "action",
            f"Install on the remote: {' '.join(missing)} (e.g. `sudo apt-get install -y ...`)",
        )
    return StepResult("tools", "ok", ", ".join(TOOLS))


def _remote_version(shell: RemoteShell) -> str | None:
    result = shell.run(["agentbox", "--version"])
    return (
        result.stdout.strip().split()[-1]
        if result.returncode == 0 and result.stdout.strip()
        else None
    )


def _agentbox(
    shell: RemoteShell,
    prompter: Prompter | None,
    local_version: str,
    wheel_builder: WheelBuilder | None,
    force: bool = False,
) -> StepResult:
    remote = _remote_version(shell)
    # Same version string does not mean same code when the laptop runs from a source checkout.
    if remote == local_version and not force:
        return StepResult("agentbox", "ok", local_version)
    found = remote or "not installed"
    if prompter is None or wheel_builder is None:
        return StepResult(
            "agentbox", "action", f"remote {found}, laptop {local_version}; run remote setup"
        )
    if not prompter.confirm(f"Install agentbox {local_version} on the remote (currently {found})?"):
        return StepResult("agentbox", "action", f"remote {found}, laptop {local_version}")
    with wheel_builder() as wheel:
        remote_wheel = None
        if wheel is not None:
            remote_wheel = f"{WHEEL_DIR}/{wheel.name}"
            shell.check(
                ["bash", "-c", 'mkdir -p "$(dirname "$1")" && base64 -d > "$1"', "_", remote_wheel],
                error="Cannot upload wheel",
                input=base64.b64encode(wheel.read_bytes()).decode(),
            )
    shell.check(
        ["pipx", "install", "--force", remote_wheel or f"agentbox=={local_version}"],
        error="pipx install failed",
    )
    if _remote_version(shell) != local_version:
        raise RemoteError("agentbox version on the remote still differs after install")
    return StepResult("agentbox", "fixed", local_version)


def _github(shell: RemoteShell) -> StepResult:
    if shell.run(["command", "-v", "gh"]).returncode != 0:
        return StepResult(
            "github",
            "action",
            "Install GitHub CLI on the remote (https://cli.github.com), then re-run",
        )
    if shell.run(["gh", "auth", "status"]).returncode == 0:
        return StepResult("github", "ok", "gh logged in")
    return StepResult(
        "github",
        "action",
        f"Run in your terminal: ssh -t {shell.destination} gh auth login "
        "--hostname github.com --web",
    )


def _repository(shell: RemoteShell, repository: str, base_dir: str, *, write: bool) -> StepResult:
    repo = f"{base_dir}/repo"
    if shell.run(["test", "-d", f"{repo}/.git"]).returncode == 0:
        origin_result = shell.run(["git", "-C", repo, "remote", "get-url", "origin"])
        if origin_result.returncode != 0:
            return StepResult("repository", "action", f"{repo} has no origin remote")
        origin = origin_result.stdout
        if origin.strip() != repository:
            return StepResult(
                "repository", "action", f"{repo} has origin {origin.strip()}, expected {repository}"
            )
        # A branch held by the primary clone cannot be checked out in a task worktree.
        if shell.run(["git", "-C", repo, "symbolic-ref", "-q", "HEAD"]).returncode != 0:
            return StepResult("repository", "ok", repo)
        if not write:
            return StepResult(
                "repository", "action", f"{repo} is on a branch; run remote setup to detach it"
            )
        _detach(shell, repo)
        return StepResult("repository", "fixed", f"{repo} (detached HEAD)")
    if not write:
        return StepResult("repository", "action", f"{repo} missing; run remote setup")
    shell.check(["mkdir", "-p", f"{base_dir}/wt"], error=f"Cannot create {base_dir}")
    shell.check(["git", "clone", repository, repo], error=f"Cannot clone {repository}")
    _detach(shell, repo)
    return StepResult("repository", "fixed", repo)


def _detach(shell: RemoteShell, repo: str) -> None:
    shell.check(["git", "-C", repo, "checkout", "--detach"], error=f"Cannot detach HEAD in {repo}")


def _desired_config(runtime: str) -> dict[str, Any]:
    return {"runtime": runtime, "credentials": {"github": True}, "state_scope": "repository"}


def _merge(
    current: dict[str, Any], desired: dict[str, Any], prefix: str = ""
) -> tuple[dict[str, Any], list[str], list[str]]:
    merged = dict(current)
    missing: list[str] = []
    conflicts: list[str] = []
    for key, value in desired.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            nested, nested_missing, nested_conflicts = _merge(
                dict(current.get(key) or {}), value, f"{path}."
            )
            merged[key] = nested
            missing += nested_missing
            conflicts += nested_conflicts
        elif key not in current:
            merged[key] = value
            missing.append(path)
        elif current[key] != value:
            conflicts.append(f"{path} is {current[key]!r}, needs {value!r}")
    return merged, missing, conflicts


def _parse_config(path: str, text: str) -> dict[str, Any] | StepResult:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return StepResult("remote-config", "action", f"{path} is not valid YAML")
    loaded = loaded or {}
    if not isinstance(loaded, dict):
        return StepResult("remote-config", "action", f"{path} does not contain a mapping")
    if not isinstance(loaded.get("credentials", {}), dict):
        return StepResult("remote-config", "action", f"{path}: 'credentials' must be a mapping")
    return loaded


def _check_tracked_config(
    shell: RemoteShell, repo_file: str, desired: dict[str, Any]
) -> StepResult:
    # Tracked in the repository and checked out into every worktree: read-only for the wizard.
    result = shell.run(["cat", repo_file])
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        return StepResult("remote-config", "action", f"Cannot read {repo_file}: {detail}")
    parsed = _parse_config(repo_file, result.stdout)
    if isinstance(parsed, StepResult):
        return parsed
    _, missing, conflicts = _merge(parsed, desired)
    if not missing and not conflicts:
        return StepResult("remote-config", "ok", repo_file)
    problems = [f"add {key}" for key in missing] + conflicts
    return StepResult(
        "remote-config",
        "action",
        f"{repo_file} is tracked in the repository and takes precedence; "
        f"edit it there: {'; '.join(problems)}",
    )


def _override(base: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in desired.items():
        merged[key] = (
            _override(dict(base.get(key) or {}), value) if isinstance(value, dict) else value
        )
    return merged


def _global_config(shell: RemoteShell) -> dict[str, Any] | StepResult:
    for candidate in GLOBAL_CONFIG_CANDIDATES:
        result = shell.run(["cat", candidate])
        if result.returncode == 0:
            return _parse_config(f"~/{candidate}", result.stdout)
    return {}


def _remote_config(
    shell: RemoteShell, prompter: Prompter | None, runtime: str, host: RemoteHost
) -> StepResult:
    desired = _desired_config(runtime)
    for name in REPO_CONFIG_NAMES:
        repo_file = f"{host.repo_dir}/{name}"
        if shell.run(["test", "-f", repo_file]).returncode == 0:
            tracked = _check_tracked_config(shell, repo_file, desired)
            if tracked.status != "ok":
                return tracked
            break

    # Commands outside a worktree (services, `agentbox build`) read this file, not a tracked one.
    target = host.config_file
    exists = shell.run(["test", "-f", target])
    if exists.returncode not in (0, 1):
        detail = exists.stderr.strip() or f"exit {exists.returncode}"
        return StepResult("remote-config", "action", f"Cannot inspect {target}: {detail}")
    if exists.returncode == 0:
        result = shell.run(["cat", target])
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            return StepResult("remote-config", "action", f"Cannot read {target}: {detail}")
        current = _parse_config(target, result.stdout)
        if isinstance(current, StepResult):
            return current
        merged, missing, conflicts = _merge(current, desired)
        if conflicts:
            return StepResult(
                "remote-config", "action", f"Edit {target} on the remote: " + "; ".join(conflicts)
            )
        if not missing:
            return StepResult("remote-config", "ok", target)
        question = f"Add {', '.join(missing)} to remote {target}?"
    else:
        # Seeded once from the remote user's global config, which itself stays untouched.
        base = _global_config(shell)
        if isinstance(base, StepResult):
            return base
        merged, (_, missing, _) = _override(base, desired), _merge({}, desired)
        question = f"Create remote {target} for agentbox remote tasks?"
    if prompter is None or not prompter.confirm(question):
        return StepResult("remote-config", "action", f"{target}: missing {', '.join(missing)}")
    shell.write_file(target, yaml.safe_dump(merged, sort_keys=False))
    return StepResult("remote-config", "fixed", f"{target}: {', '.join(missing)}")


def _image(shell: RemoteShell, host: RemoteHost) -> StepResult:
    shell.check(
        [
            "bash",
            "-c",
            'cd "$1" && shift && "$@"',
            "_",
            host.repo_dir,
            *host.agentbox("build", "--agent", host.agent),
        ],
        error=f"Cannot build the {host.agent} image",
    )
    return StepResult("image", "ok", host.agent)


def _ssh_command(destination: str, command: list[str]) -> str:
    # ssh re-joins its arguments for the remote shell, so the remote part is quoted twice.
    remote = shlex.join(["bash", "-lc", shlex.join(command)])
    quoted = f'"{remote}"' if _DOUBLE_QUOTE_SAFE.fullmatch(remote) else shlex.quote(remote)
    return f"ssh -t {shlex.quote(destination)} {quoted}"


def _login_hint(shell: RemoteShell, host: RemoteHost) -> StepResult:
    command = _ssh_command(
        shell.destination, host.agentbox("run", host.repo_dir, "--agent", host.agent)
    )
    return StepResult("login", "info", f"Log the agent in once: {command}")


def run_setup(
    name: str,
    shell: RemoteShell,
    prompter: Prompter,
    *,
    local_version: str,
    wheel_builder: WheelBuilder,
    registry: Path | None = None,
    force_reinstall: bool = False,
) -> list[StepResult]:
    existing = load_registry(registry).get(name)
    results: list[StepResult] = []

    def stop() -> bool:
        return results[-1].status == "action"

    results.append(_ssh(shell))
    if stop():
        return results
    runtime_result, runtime = _runtime(shell, existing.runtime if existing else None)
    results.append(runtime_result)
    if stop() or runtime is None:
        return results
    results.append(_tools(shell))
    if stop():
        return results
    results.append(_agentbox(shell, prompter, local_version, wheel_builder, force_reinstall))
    if stop():
        return results
    results.append(_github(shell))
    if stop():
        return results
    repository = (
        existing.repository if existing else prompter.ask("Git repository URL (repository)")
    )
    base_dir = (
        existing.base_dir
        if existing
        else prompter.ask("Absolute directory on the remote (base_dir)")
    )
    agent = existing.agent if existing else prompter.ask("Default agent (agent)")
    try:
        host = RemoteHost(
            ssh=shell.destination,
            repository=repository,
            base_dir=base_dir,
            agent=agent,
            runtime=cast(Literal["podman", "docker"], runtime),
        )
    except ValidationError as err:
        results.append(StepResult("registry", "action", str(err)))
        return results
    results.append(_repository(shell, host.repository, host.base_dir, write=True))
    if stop():
        return results
    results.append(_remote_config(shell, prompter, runtime, host))
    if stop():
        return results
    results.append(_image(shell, host))
    if stop():
        return results
    if existing != host:
        save_host(name, host, registry)
        results.append(StepResult("save", "fixed", name))
    else:
        results.append(StepResult("save", "ok", name))
    results.append(_login_hint(shell, host))
    return results


def run_doctor(host: RemoteHost, shell: RemoteShell, *, local_version: str) -> list[StepResult]:
    results = [_ssh(shell)]
    if results[-1].status == "action":
        return results
    runtime_result, _ = _runtime(shell, host.runtime)
    results += [
        runtime_result,
        _tools(shell),
        _agentbox(shell, None, local_version, None),
        _github(shell),
        _repository(shell, host.repository, host.base_dir, write=False),
        _remote_config(shell, None, host.runtime, host),
        _login_hint(shell, host),
    ]
    return results
