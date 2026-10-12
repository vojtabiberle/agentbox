from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field

from agentbox.remote_ssh import CommandResult

OK = CommandResult(0, "", "")


def fail(stderr: str = "boom", code: int = 1) -> CommandResult:
    return CommandResult(code, "", stderr)


def out(stdout: str) -> CommandResult:
    return CommandResult(0, stdout, "")


@dataclass
class FakeCall:
    argv: list[str]
    input: str | None
    tty: bool

    @property
    def remote(self) -> str:
        # ssh argv ends with "bash -lc '<command>'"; unwrap to the inner command.
        return shlex.split(self.argv[-1])[-1]


@dataclass
class FakeRunner:
    responses: dict[str, CommandResult] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, input: str | None = None, tty: bool = False
    ) -> CommandResult:
        call = FakeCall(list(argv), input, tty)
        self.calls.append(call)
        for needle, result in self.responses.items():
            if needle in call.remote:
                return result
        return OK

    def remote_commands(self) -> list[str]:
        return [call.remote for call in self.calls]
