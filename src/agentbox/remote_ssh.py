"""SSH transport for remote commands."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .exceptions import RemoteError


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, input: str | None = None, tty: bool = False
    ) -> CommandResult: ...


def subprocess_runner(
    argv: Sequence[str], *, input: str | None = None, tty: bool = False
) -> CommandResult:
    if tty:
        return CommandResult(subprocess.run(list(argv)).returncode, "", "")
    completed = subprocess.run(list(argv), input=input, capture_output=True, text=True)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class RemoteShell:
    def __init__(self, destination: str, runner: CommandRunner = subprocess_runner) -> None:
        self.destination = destination
        self._runner = runner

    def argv(self, command: Sequence[str], *, tty: bool = False) -> list[str]:
        # A login shell puts pipx/user tools on PATH for non-interactive ssh sessions.
        remote = shlex.join(["bash", "-lc", shlex.join(command)])
        return ["ssh", "-t" if tty else "-T", "-o", "BatchMode=yes", "--", self.destination, remote]

    def run(self, command: Sequence[str], *, input: str | None = None) -> CommandResult:
        return self._runner(self.argv(command), input=input)

    def check(self, command: Sequence[str], *, error: str, input: str | None = None) -> str:
        result = self.run(command, input=input)
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            raise RemoteError(f"{error}: {detail}")
        return result.stdout

    def interactive(self, command: Sequence[str]) -> int:
        return self._runner(self.argv(command, tty=True), tty=True).returncode

    def write_file(self, relative_path: str, content: str) -> None:
        self.check(
            ["bash", "-c", 'mkdir -p "$(dirname "$1")" && cat > "$1"', "_", relative_path],
            error=f"Cannot write {relative_path}",
            input=content,
        )
