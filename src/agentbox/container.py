"""Container runtime abstraction for Podman and Docker."""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Literal

from .exceptions import ConfigError, RuntimeNotFoundError
from .execution import RunSpec
from .state import record_runtime, state_lease


class ContainerRuntime:
    """Abstraction over Podman and Docker container runtimes."""

    def __init__(self, runtime: Literal["podman", "docker"]) -> None:
        self.runtime = runtime
        self._verify_runtime()

    def _verify_runtime(self) -> None:
        """Verify the container runtime is available."""
        try:
            subprocess.run(
                [self.runtime, "--version"],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as err:
            raise RuntimeNotFoundError(self.runtime) from err
        except subprocess.CalledProcessError as err:
            raise RuntimeNotFoundError(self.runtime) from err

    def image_exists(self, name: str) -> bool:
        """Check if a container image exists."""
        # Podman has `image exists`, Docker uses `image inspect`
        if self.runtime == "podman":
            cmd = [self.runtime, "image", "exists", name]
        else:
            cmd = [self.runtime, "image", "inspect", name]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0

    def pull(self, image: str) -> None:
        """Pull an explicitly selected image using runtime registry authentication."""
        subprocess.run([self.runtime, "pull", image], check=True)

    def check_executables(self, image: str, executables: list[str]) -> None:
        """Probe image compatibility without host mounts, credentials or networking."""
        if not executables:
            return
        if any(not re.fullmatch(r"[A-Za-z0-9_.+-]+", tool) for tool in executables):
            raise ConfigError("Invalid executable name in image requirements")
        name = f"agentbox-probe-{uuid.uuid4().hex}"
        try:
            result = subprocess.run(
                [
                    self.runtime,
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--user",
                    "65534:65534",
                    "--entrypoint",
                    "/bin/sh",
                    image,
                    "-c",
                    'for tool; do command -v "$tool" >/dev/null || { '
                    'printf "%s\\n" "$tool"; failed=1; }; done; exit "${failed:-0}"',
                    "agentbox-check",
                    *executables,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as err:
            try:
                subprocess.run(
                    [self.runtime, "rm", "-f", name], capture_output=True, check=True, timeout=10
                )
            except (OSError, subprocess.SubprocessError) as cleanup_error:
                raise ConfigError(
                    f"Image probe timed out; remove container {name} manually"
                ) from cleanup_error
            raise ConfigError("Image executable probe timed out; container removed") from err
        except (OSError, subprocess.SubprocessError) as err:
            raise ConfigError(
                "Cannot check image executables; verify runtime/image compatibility"
            ) from err
        if result.returncode:
            missing = sorted(set(result.stdout.splitlines()) & set(executables))
            detail = ", ".join(missing) if missing else "probe failed"
            raise ConfigError(f"Image does not satisfy required executables: {detail}")

    def image_id(self, image: str) -> str:
        """Resolve a mutable image tag before composing a project extension."""
        result = subprocess.run(
            [self.runtime, "image", "inspect", "--format", "{{.Id}}", image],
            check=True,
            capture_output=True,
            text=True,
        )
        identity = result.stdout.strip()
        if not identity or any(char.isspace() for char in identity):
            raise ConfigError("Container runtime returned an invalid image ID")
        return identity

    def build(self, dockerfile_content: str, tag: str, context: Path | None = None) -> None:
        """Build a container image from Dockerfile content."""
        subprocess.run(
            [self.runtime, "build", "-t", tag, "-f", "-", str(context) if context else "."],
            input=dockerfile_content.encode(),
            check=True,
        )

    def run(self, spec: RunSpec) -> None:
        """Replace this process with the prepared container."""
        cmd = self.build_command(spec)
        if spec.home is None:
            os.execvp(cmd[0], cmd)
            return
        with state_lease(spec.home):
            if not spec.home.is_dir():
                raise ConfigError("Private HOME disappeared before startup; retry the run")
            record_runtime(spec.home, self.runtime)
            os.execvp(cmd[0], cmd)

    def build_command(self, spec: RunSpec) -> list[str]:
        """Render runtime arguments without starting a container."""
        cmd = [self.runtime, "run", "--rm", "--init"]
        for option, value in (
            ("--memory", spec.memory),
            ("--cpus", spec.cpus),
            ("--pids-limit", spec.pids_limit),
        ):
            if value is not None:
                cmd.extend([option, str(value)])
        if spec.network == "none":
            cmd.append("--network=none")
        if spec.interactive:
            cmd.append("-it")
        elif spec.stdin:
            cmd.append("-i")
        if spec.name is not None:
            cmd.extend(["--name", spec.name])
        cmd.extend(["-w", "/workspace"])
        if spec.share_hostname:
            cmd.append("--uts=host")
        if self.runtime == "podman":
            cmd.extend(["--userns=keep-id", "--security-opt=no-new-privileges"])
        else:
            user = "0:0" if self.is_rootless_docker() else f"{os.getuid()}:{os.getgid()}"
            cmd.extend(["--user", user])
        for mount in spec.mounts:
            mode = "ro" if mount.readonly else "rw"
            suffix = self._vol_suffix(mode) if mount.relabel else f":{mode}"
            cmd.extend(["-v", f"{mount.source}:{mount.target}{suffix}"])
        environment = {
            "TERM": os.environ.get("TERM", "xterm-256color"),
            "COLUMNS": self._get_terminal_columns(),
            "LINES": self._get_terminal_lines(),
            **dict(spec.environment),
        }
        for key, value in environment.items():
            cmd.extend(["-e", f"{key}={value}"])
        for key in spec.forwarded_env:
            cmd.extend(["-e", key])
        return [*cmd, spec.image, *spec.command]

    def is_rootless_docker(self) -> bool:
        """Detect daemon UID mapping, honoring Docker context/DOCKER_HOST."""
        if self.runtime != "docker":
            return False
        try:
            result = subprocess.run(
                [self.runtime, "info", "--format", "{{json .SecurityOptions}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            options = json.loads(result.stdout)
        except (subprocess.CalledProcessError, ValueError) as err:
            raise ConfigError("Cannot determine Docker daemon security mode") from err
        if not isinstance(options, list) or not all(isinstance(item, str) for item in options):
            raise ConfigError("Docker returned invalid security options")
        return "name=rootless" in options

    @staticmethod
    def _get_terminal_columns() -> str:
        """Get terminal column count from env or OS, fallback to 80."""
        if "COLUMNS" in os.environ:
            return os.environ["COLUMNS"]
        try:
            return str(os.get_terminal_size().columns)
        except (ValueError, OSError):
            return "80"

    @staticmethod
    def _get_terminal_lines() -> str:
        """Get terminal line count from env or OS, fallback to 24."""
        if "LINES" in os.environ:
            return os.environ["LINES"]
        try:
            return str(os.get_terminal_size().lines)
        except (ValueError, OSError):
            return "24"

    def _vol_suffix(self, mode: str = "") -> str:
        """Get volume suffix based on runtime. Mode can be 'ro' or 'rw' or empty."""
        if self.runtime == "podman":
            # Podman needs :Z for SELinux relabeling
            if mode:
                return f":{mode},Z"
            return ":Z"
        else:
            # Docker doesn't need SELinux labels
            if mode:
                return f":{mode}"
            return ""
