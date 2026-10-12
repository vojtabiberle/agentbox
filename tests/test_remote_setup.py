import shlex
import subprocess
import tempfile
from collections.abc import Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from agentbox.exceptions import RemoteError
from agentbox.remote_registry import RemoteHost, get_host, save_host
from agentbox.remote_setup import StepResult, _ssh_command, local_wheel, run_doctor, run_setup
from agentbox.remote_ssh import RemoteShell
from tests.remote_fakes import FakeRunner, fail, out

VERSION = "0.5.0a1"
DESIRED = {"runtime": "docker", "credentials": {"github": True}, "state_scope": "repository"}
SCOPED = "/srv/ab/r/agentbox.yaml"
GLOBAL = ".config/agentbox/config.yaml"


def _no_wheel() -> nullcontext[None]:
    return nullcontext(None)


class ScriptedPrompter:
    def __init__(self, answers: dict[str, str] | None = None, confirm: bool = True) -> None:
        self.answers = answers or {}
        self.confirm_value = confirm
        self.asked: list[str] = []
        self.confirmed: list[str] = []

    def ask(self, text: str, default: str | None = None) -> str:
        self.asked.append(text)
        for key, value in self.answers.items():
            if key in text:
                return value
        assert default is not None, f"unexpected prompt: {text}"
        return default

    def confirm(self, text: str) -> bool:
        self.confirmed.append(text)
        return self.confirm_value


ANSWERS = {"repository": "git@github.com:o/r.git", "base_dir": "/srv/ab/r", "agent": "claude"}


def _healthy(**overrides: object) -> FakeRunner:
    responses = {
        "podman info": fail("no podman"),
        "agentbox --version": out(f"agentbox, version {VERSION}\n"),
        "remote get-url origin": out("git@github.com:o/r.git\n"),
        "symbolic-ref -q HEAD": fail(""),
        # No repo-tracked config by default; remote tasks use the scoped file under base_dir.
        "test -f /srv/ab/r/repo/.agentbox.yaml": fail(""),
        "test -f /srv/ab/r/repo/.agentbox.yml": fail(""),
        f"cat {SCOPED}": out(yaml.safe_dump(DESIRED)),
    }
    responses.update(overrides)  # type: ignore[arg-type]
    return FakeRunner(responses)


def _statuses(results: list[StepResult]) -> dict[str, str]:
    return {r.name: r.status for r in results}


def test_ssh_failure_stops_immediately(tmp_path: Path) -> None:
    runner = FakeRunner({"true": fail("Permission denied (publickey)")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].status == "action" and "Permission denied" in results[-1].detail
    assert len(runner.calls) == 1


def test_missing_runtime_is_action_without_sudo(tmp_path: Path) -> None:
    runner = _healthy(**{"docker info": fail("permission denied")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "runtime" and results[-1].status == "action"
    assert not any("sudo" in c for c in runner.remote_commands())


def test_setup_is_idempotent(tmp_path: Path) -> None:
    registry = tmp_path / "r.yaml"
    save_host(
        "vm",
        RemoteHost(
            ssh="vm",
            repository="git@github.com:o/r.git",
            base_dir="/srv/ab/r",
            agent="claude",
            runtime="docker",
        ),
        registry,
    )
    prompter = ScriptedPrompter()
    runner = _healthy()
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        prompter,
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=registry,
    )
    assert prompter.confirmed == []
    assert all(r.status in {"ok", "info"} for r in results)
    assert not any(c.input is not None for c in runner.calls)
    assert not any("git clone" in c for c in runner.remote_commands())


def test_version_mismatch_installs_then_verifies(tmp_path: Path) -> None:
    # The fake keeps reporting the old version, so post-install verification must fail loudly.
    runner = _healthy(**{"agentbox --version": out("agentbox, version 0.4.0\n")})
    with pytest.raises(RemoteError, match="still differs"):
        run_setup(
            "vm",
            RemoteShell("vm", runner),
            ScriptedPrompter(ANSWERS),
            local_version=VERSION,
            wheel_builder=_no_wheel,
            registry=tmp_path / "r.yaml",
        )
    assert f"pipx install --force agentbox=={VERSION}" in runner.remote_commands()


def test_wheel_is_streamed_not_copied_with_scp(tmp_path: Path) -> None:
    wheel = tmp_path / "agentbox-0.5.0a1-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes")
    runner = _healthy(**{"agentbox --version": fail("command not found")})
    with pytest.raises(RemoteError, match="still differs"):
        run_setup(
            "vm",
            RemoteShell("vm", runner),
            ScriptedPrompter(ANSWERS),
            local_version=VERSION,
            wheel_builder=lambda: nullcontext(wheel),
            registry=tmp_path / "r.yaml",
        )
    uploads = [c for c in runner.calls if c.input is not None]
    assert uploads and "base64 -d" in uploads[0].remote
    assert f"pipx install --force .cache/agentbox/{wheel.name}" in runner.remote_commands()
    assert not any(c.argv[0] == "scp" for c in runner.calls)


def test_declined_install_is_action(tmp_path: Path) -> None:
    runner = _healthy(**{"agentbox --version": fail("command not found")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS, confirm=False),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "agentbox" and results[-1].status == "action"


def test_gh_not_logged_in_prints_command_without_token(tmp_path: Path) -> None:
    runner = _healthy(**{"gh auth status": fail("not logged in")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "github" and results[-1].status == "action"
    assert "ssh -t vm gh auth login --hostname github.com --web" in results[-1].detail


def test_clones_missing_repository(tmp_path: Path) -> None:
    runner = _healthy(**{"test -d /srv/ab/r/repo/.git": fail("")})
    run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    cmds = runner.remote_commands()
    clone = cmds.index("git clone git@github.com:o/r.git /srv/ab/r/repo")
    assert cmds[clone + 1] == "git -C /srv/ab/r/repo checkout --detach"


def test_existing_clone_on_branch_is_detached(tmp_path: Path) -> None:
    runner = _healthy(**{"symbolic-ref -q HEAD": out("refs/heads/main\n")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert _statuses(results)["repository"] == "fixed"
    assert "git -C /srv/ab/r/repo checkout --detach" in runner.remote_commands()


def test_doctor_reports_attached_clone_without_detaching() -> None:
    host = RemoteHost(
        ssh="vm",
        repository="git@github.com:o/r.git",
        base_dir="/srv/ab/r",
        agent="claude",
        runtime="docker",
    )
    runner = _healthy(**{"symbolic-ref -q HEAD": out("refs/heads/main\n")})
    results = run_doctor(host, RemoteShell("vm", runner), local_version=VERSION)
    assert _statuses(results)["repository"] == "action"
    assert not any("checkout" in c for c in runner.remote_commands())


def test_successful_setup_saves_registry(tmp_path: Path) -> None:
    registry = tmp_path / "r.yaml"
    results = run_setup(
        "vm",
        RemoteShell("vm", _healthy()),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=registry,
    )
    assert _statuses(results)["save"] == "fixed"
    assert get_host("vm", registry).runtime == "docker"


def test_doctor_never_writes(tmp_path: Path) -> None:
    host = RemoteHost(
        ssh="vm",
        repository="git@github.com:o/r.git",
        base_dir="/srv/ab/r",
        agent="claude",
        runtime="docker",
    )
    runner = _healthy(
        **{
            "agentbox --version": out("agentbox, version 0.4.0\n"),
            "cat .config/agentbox/config.yaml": fail("No such file"),
        }
    )
    results = run_doctor(host, RemoteShell("vm", runner), local_version=VERSION)
    assert _statuses(results)["agentbox"] == "action"
    assert not any(c.input is not None for c in runner.calls)
    assert not any(
        word in c
        for c in runner.remote_commands()
        for word in ("pipx install", "git clone", "agentbox build")
    )


def test_repo_tracked_config_wins_and_is_not_written(tmp_path: Path) -> None:
    runner = _healthy(**{"test -f /srv/ab/r/repo/.agentbox.yaml": out("")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "remote-config" and results[-1].status == "action"
    assert "/srv/ab/r/repo/.agentbox.yaml" in results[-1].detail
    assert not any(c.input is not None for c in runner.calls)


def test_relative_base_dir_is_action_named_registry(tmp_path: Path) -> None:
    answers = {"repository": "git@github.com:o/r.git", "base_dir": "srv/ab/r", "agent": "claude"}
    results = run_setup(
        "vm",
        RemoteShell("vm", _healthy()),
        ScriptedPrompter(answers),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "registry" and results[-1].status == "action"


def test_missing_origin_is_action(tmp_path: Path) -> None:
    runner = _healthy(**{"remote get-url origin": fail("no such remote 'origin'")})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "repository" and results[-1].status == "action"
    assert "no origin remote" in results[-1].detail


def _setup(runner: FakeRunner, tmp_path: Path) -> list[StepResult]:
    return run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )


def _tracked(content: str) -> FakeRunner:
    return _healthy(
        **{
            "test -f /srv/ab/r/repo/.agentbox.yaml": out(""),
            "cat /srv/ab/r/repo/.agentbox.yaml": out(content),
        }
    )


def test_repo_tracked_config_with_matching_keys_is_ok(tmp_path: Path) -> None:
    runner = _tracked(yaml.safe_dump({**DESIRED, "extra": 1}))
    results = _setup(runner, tmp_path)
    assert _statuses(results)["remote-config"] == "ok"
    assert _statuses(results)["save"] == "fixed"
    assert not any(c.input is not None for c in runner.calls)


def test_repo_tracked_config_names_only_missing_and_conflicting_keys(tmp_path: Path) -> None:
    runner = _tracked(yaml.safe_dump({"runtime": "podman", "credentials": {"github": True}}))
    results = _setup(runner, tmp_path)
    last = results[-1]
    assert last.name == "remote-config" and last.status == "action"
    assert "/srv/ab/r/repo/.agentbox.yaml" in last.detail
    assert "state_scope" in last.detail and "runtime is 'podman'" in last.detail
    assert "credentials" not in last.detail
    assert not any(c.input is not None for c in runner.calls)


@pytest.mark.parametrize("content", ["runtime: [unterminated\n", "- a\n- b\n"])
def test_repo_tracked_config_malformed_is_action(tmp_path: Path, content: str) -> None:
    runner = _tracked(content)
    results = _setup(runner, tmp_path)
    assert results[-1].name == "remote-config" and results[-1].status == "action"
    assert "/srv/ab/r/repo/.agentbox.yaml" in results[-1].detail
    assert not any(c.input is not None for c in runner.calls)


def test_login_hint_uses_login_shell(tmp_path: Path) -> None:
    results = _setup(_healthy(), tmp_path)
    hint = results[-1]
    assert hint.name == "login"
    command = hint.detail.split(": ", 1)[1]
    ssh = shlex.split(command)
    assert ssh[:3] == ["ssh", "-t", "vm"]
    # ssh joins its remaining arguments with spaces and the remote shell re-parses them.
    remote = shlex.split(" ".join(ssh[3:]))
    assert remote[:2] == ["bash", "-lc"]
    assert shlex.split(remote[2]) == [
        "env",
        f"AGENTBOX_CONFIG={SCOPED}",
        "agentbox",
        "run",
        "/srv/ab/r/repo",
        "--agent",
        "claude",
    ]


def test_missing_gh_is_action_with_install_hint(tmp_path: Path) -> None:
    runner = _healthy(**{"command -v gh": fail("")})
    results = _setup(runner, tmp_path)
    assert results[-1].name == "github" and results[-1].status == "action"
    assert "https://cli.github.com" in results[-1].detail
    assert not any("gh auth status" in c for c in runner.remote_commands())


def _wheel_dirs(root: Path) -> list[Path]:
    return list(root.glob("agentbox-wheel-*"))


def test_local_wheel_removes_temp_dir_after_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    def fake_run(argv: Sequence[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        target = Path(argv[argv.index("-w") + 1])
        (target / "agentbox-0.5.0-py3-none-any.whl").write_bytes(b"w")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    with patch("agentbox.remote_setup.subprocess.run", fake_run):
        with local_wheel() as wheel:
            assert wheel is not None and wheel.read_bytes() == b"w"
    assert _wheel_dirs(tmp_path) == []


def test_local_wheel_pip_failure_is_remote_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    error = subprocess.CalledProcessError(1, ["pip"], output=b"", stderr=b"pip exploded")
    with patch("agentbox.remote_setup.subprocess.run", side_effect=error):
        with pytest.raises(RemoteError, match="pip exploded"):
            with local_wheel():
                pass
    assert _wheel_dirs(tmp_path) == []


def test_local_wheel_without_output_is_remote_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    done = subprocess.CompletedProcess(["pip"], 0, b"", b"")
    with patch("agentbox.remote_setup.subprocess.run", return_value=done):
        with pytest.raises(RemoteError, match="wheel"):
            with local_wheel():
                pass
    assert _wheel_dirs(tmp_path) == []


@pytest.mark.parametrize("repo", ["/srv/ab/r/repo", "/srv/my repo", "/srv/$HOME's"])
def test_ssh_command_survives_both_shells(repo: str) -> None:
    ssh = shlex.split(_ssh_command("vm", ["agentbox", "run", repo]))
    remote = shlex.split(" ".join(ssh[3:]))
    assert remote[:2] == ["bash", "-lc"]
    assert shlex.split(remote[2]) == ["agentbox", "run", repo]


def test_force_reinstall_installs_same_version_after_confirmation(tmp_path: Path) -> None:
    registry = tmp_path / "r.yaml"
    save_host(
        "vm",
        RemoteHost(
            ssh="vm",
            repository="git@github.com:o/r.git",
            base_dir="/srv/ab/r",
            agent="claude",
            runtime="docker",
        ),
        registry,
    )
    prompter = ScriptedPrompter()
    runner = _healthy()
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        prompter,
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=registry,
        force_reinstall=True,
    )
    assert any("agentbox" in text for text in prompter.confirmed)
    assert f"pipx install --force agentbox=={VERSION}" in runner.remote_commands()
    assert {r.name: r.status for r in results}["agentbox"] == "fixed"


def _writes(runner: FakeRunner) -> list[Any]:
    return [c for c in runner.calls if c.input is not None]


def test_remote_config_is_created_under_base_dir_not_global(tmp_path: Path) -> None:
    global_config = {"runtime": "podman", "toolsets": ["base", "go"], "credentials": {"aws": True}}
    runner = _healthy(
        **{
            f"test -f {SCOPED}": fail("", 1),
            f"cat {GLOBAL}": out(yaml.safe_dump(global_config)),
        }
    )
    results = _setup(runner, tmp_path)
    assert _statuses(results)["remote-config"] == "fixed"
    writes = _writes(runner)
    assert len(writes) == 1 and writes[0].remote.endswith(SCOPED)
    # Seeded from the global file, with the remote-task keys overriding it.
    assert yaml.safe_load(writes[0].input) == {
        "runtime": "docker",
        "toolsets": ["base", "go"],
        "credentials": {"aws": True, "github": True},
        "state_scope": "repository",
    }


def test_remote_config_created_from_scratch_without_global(tmp_path: Path) -> None:
    runner = _healthy(**{f"test -f {SCOPED}": fail("", 1), "cat .config": fail("No such file")})
    _setup(runner, tmp_path)
    assert yaml.safe_load(_writes(runner)[-1].input) == DESIRED


def test_remote_config_creation_needs_confirmation(tmp_path: Path) -> None:
    runner = _healthy(**{f"test -f {SCOPED}": fail("", 1)})
    results = run_setup(
        "vm",
        RemoteShell("vm", runner),
        ScriptedPrompter(ANSWERS, confirm=False),
        local_version=VERSION,
        wheel_builder=_no_wheel,
        registry=tmp_path / "r.yaml",
    )
    assert results[-1].name == "remote-config" and results[-1].status == "action"
    assert not _writes(runner)


def test_remote_config_adds_missing_keys_to_scoped_file(tmp_path: Path) -> None:
    runner = _healthy(**{f"cat {SCOPED}": out(yaml.safe_dump({"toolsets": ["base"]}))})
    results = _setup(runner, tmp_path)
    assert _statuses(results)["remote-config"] == "fixed"
    assert yaml.safe_load(_writes(runner)[-1].input) == {"toolsets": ["base"], **DESIRED}


def test_remote_config_conflict_in_scoped_file_not_overwritten(tmp_path: Path) -> None:
    runner = _healthy(**{f"cat {SCOPED}": out("runtime: podman\n")})
    results = _setup(runner, tmp_path)
    assert results[-1].name == "remote-config" and results[-1].status == "action"
    assert SCOPED in results[-1].detail and "runtime" in results[-1].detail
    assert not _writes(runner)


@pytest.mark.parametrize("content", ["runtime: [unterminated\n", "- just\n- a\n- list\n"])
def test_remote_config_malformed_scoped_file_is_action(tmp_path: Path, content: str) -> None:
    runner = _healthy(**{f"cat {SCOPED}": out(content)})
    results = _setup(runner, tmp_path)
    assert results[-1].name == "remote-config" and results[-1].status == "action"
    assert not _writes(runner)


def test_remote_config_ssh_failure_is_action(tmp_path: Path) -> None:
    runner = _healthy(**{f"test -f {SCOPED}": fail("Connection reset", 255)})
    results = _setup(runner, tmp_path)
    assert results[-1].name == "remote-config" and results[-1].status == "action"
    assert "Connection reset" in results[-1].detail
    assert not _writes(runner)


def test_setup_never_touches_global_config(tmp_path: Path) -> None:
    runner = _healthy(**{f"test -f {SCOPED}": fail("", 1)})
    _setup(runner, tmp_path)
    assert not any(GLOBAL in c.remote for c in _writes(runner))


def test_tracked_config_ok_still_manages_scoped_file(tmp_path: Path) -> None:
    runner = _tracked(yaml.safe_dump(DESIRED))
    runner.responses[f"test -f {SCOPED}"] = fail("", 1)
    results = _setup(runner, tmp_path)
    assert _statuses(results)["remote-config"] == "fixed"
    assert _writes(runner)[-1].remote.endswith(SCOPED)


def test_image_build_uses_scoped_config(tmp_path: Path) -> None:
    runner = _healthy()
    _setup(runner, tmp_path)
    build = next(c for c in runner.remote_commands() if "agentbox build" in c)
    assert shlex.split(build)[3:] == [
        "_",
        "/srv/ab/r/repo",
        "env",
        f"AGENTBOX_CONFIG={SCOPED}",
        "agentbox",
        "build",
        "--agent",
        "claude",
    ]
