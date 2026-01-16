"""Container runtime abstraction for Podman and Docker."""

import os
import subprocess
from pathlib import Path
from typing import Literal

from .config import Config
from .exceptions import RuntimeNotFoundError


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
        except FileNotFoundError:
            raise RuntimeNotFoundError(self.runtime)

    def image_exists(self, name: str) -> bool:
        """Check if a container image exists."""
        result = subprocess.run(
            [self.runtime, "image", "exists", name],
            capture_output=True,
        )
        return result.returncode == 0

    def build(self, dockerfile_content: str, tag: str) -> None:
        """Build a container image from Dockerfile content."""
        subprocess.run(
            [self.runtime, "build", "-t", tag, "-f", "-", "."],
            input=dockerfile_content.encode(),
            check=True,
        )

    def run(
        self,
        image: str,
        workspace: Path,
        ro_mounts: list[Path],
        command: list[str],
        config: Config,
    ) -> None:
        """Run a container interactively."""
        # Use host's home path for consistent identity
        host_home = str(Path.home())

        # Build command
        cmd = [
            self.runtime, "run", "-it", "--rm",
            "-v", f"{workspace}:/workspace{self._vol_suffix()}",
            "-w", "/workspace",
            "--uts=host",  # Share UTS namespace (hostname) with host
            "-e", f"TERM={os.environ.get('TERM', 'xterm-256color')}",
            "-e", f"HOME={host_home}",
            "-e", f"PATH=/usr/local/bin:/usr/bin:/bin:{host_home}/.cargo/bin",
        ]

        # Mount host machine-id for consistent identity (needed for Claude statsig cache)
        machine_id = Path("/etc/machine-id")
        if machine_id.exists():
            cmd.extend(["-v", f"{machine_id}:/etc/machine-id:ro"])

        # Add runtime-specific options for rootless operation
        if self.runtime == "podman":
            cmd.extend([
                "--userns=keep-id",
                "--security-opt=no-new-privileges",
            ])
        elif self.runtime == "docker":
            # Docker: run as current user to avoid root
            cmd.extend([
                "--user", f"{os.getuid()}:{os.getgid()}",
            ])

        # Add read-only mounts
        for i, ro_path in enumerate(ro_mounts):
            cmd.extend(["-v", f"{ro_path}:/mnt/ro{i}{self._vol_suffix('ro')}"])

        # Add Claude config mount
        self._add_claude_mounts(cmd, config)

        # Add credential mounts
        self._add_credential_mounts(cmd, config)

        # Add image and command
        cmd.append(image)
        cmd.extend(command)

        # Replace current process with container
        os.execvp(cmd[0], cmd)

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

    def _add_credential_mounts(self, cmd: list[str], config: Config) -> None:
        """Add credential directory mounts based on config."""
        creds = config.credentials
        host_home = Path.home()
        ro = self._vol_suffix("ro")

        if creds.github:
            gh_config = host_home / ".config" / "gh"
            if gh_config.exists():
                cmd.extend(["-v", f"{gh_config}:{host_home}/.config/gh{ro}"])

        if creds.azure:
            azure_dir = host_home / ".azure"
            if azure_dir.exists():
                cmd.extend(["-v", f"{azure_dir}:{host_home}/.azure{ro}"])

        if creds.aws:
            aws_dir = host_home / ".aws"
            if aws_dir.exists():
                cmd.extend(["-v", f"{aws_dir}:{host_home}/.aws{ro}"])

        if creds.gcloud:
            gcloud_dir = host_home / ".config" / "gcloud"
            if gcloud_dir.exists():
                cmd.extend(["-v", f"{gcloud_dir}:{host_home}/.config/gcloud{ro}"])

    def _add_claude_mounts(self, cmd: list[str], config: Config) -> None:
        """Add Claude config mounts."""
        host_home = Path.home()
        claude_dir = host_home / ".claude"
        claude_json = host_home / ".claude.json"
        rw = self._vol_suffix("rw")
        ro = self._vol_suffix("ro")

        if claude_dir.exists():
            cmd.extend(["-v", f"{claude_dir}:{host_home}/.claude{rw}"])

        # Claude also uses ~/.claude.json directly in home (separate from ~/.claude/.claude.json)
        if claude_json.exists():
            cmd.extend(["-v", f"{claude_json}:{host_home}/.claude.json{rw}"])

        # Additional mounts (override files in .claude)
        claude_config = config.claude

        if claude_config.global_claude_md and claude_config.global_claude_md.exists():
            cmd.extend([
                "-v", f"{claude_config.global_claude_md}:{host_home}/.claude/CLAUDE.md{ro}"
            ])

        if claude_config.plugins_dir and claude_config.plugins_dir.exists():
            cmd.extend([
                "-v", f"{claude_config.plugins_dir}:{host_home}/.claude/plugins{ro}"
            ])
