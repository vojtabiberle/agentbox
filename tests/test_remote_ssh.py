import shlex

import pytest

from agentbox.exceptions import RemoteError
from agentbox.remote_ssh import RemoteShell
from tests.remote_fakes import FakeRunner, fail, out


def test_argv_uses_batch_mode_and_login_shell() -> None:
    argv = RemoteShell("host").argv(["echo", "a b"])
    assert argv[:6] == ["ssh", "-T", "-o", "BatchMode=yes", "--", "host"]
    assert shlex.split(argv[-1]) == ["bash", "-lc", "echo 'a b'"]


def test_metacharacters_stay_quoted() -> None:
    argv = RemoteShell("host").argv(["echo", "$(rm -rf ~); x"])
    assert shlex.split(shlex.split(argv[-1])[-1]) == ["echo", "$(rm -rf ~); x"]


def test_destination_follows_option_terminator() -> None:
    argv = RemoteShell("-oProxyCommand=evil").argv(["true"])
    assert argv.index("--") == argv.index("-oProxyCommand=evil") - 1


def test_tty_flag() -> None:
    assert RemoteShell("host").argv(["true"], tty=True)[1] == "-t"


def test_check_surfaces_stderr() -> None:
    shell = RemoteShell("host", FakeRunner({"git": fail("fatal: nope")}))
    with pytest.raises(RemoteError, match="Cannot fetch: fatal: nope"):
        shell.check(["git", "fetch"], error="Cannot fetch")


def test_check_returns_stdout() -> None:
    shell = RemoteShell("host", FakeRunner({"echo": out("hi\n")}))
    assert shell.check(["echo", "hi"], error="x") == "hi\n"


def test_write_file_streams_content_via_stdin() -> None:
    runner = FakeRunner()
    RemoteShell("host", runner).write_file(".config/agentbox/config.yaml", "a: 1\n")
    call = runner.calls[-1]
    assert call.input == "a: 1\n"
    assert ".config/agentbox/config.yaml" in call.remote
