"""Deletion boundaries and concurrent state use."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from agentbox.cli import main
from agentbox.exceptions import ConfigError
from agentbox.state import record_runtime, reset_state, state_home, state_lease, state_size


def test_reset_is_scoped_and_lease_blocks_deletion(tmp_path):
    home = state_home(tmp_path, tmp_path / "project", "hermes")
    other = state_home(tmp_path, tmp_path / "project", "claude")
    home.mkdir(parents=True)
    other.mkdir(parents=True)
    (home / "memory").write_text("remember")
    with state_lease(home), pytest.raises(ConfigError, match="in use"):
        reset_state(home, "docker")
    assert (home / "memory").exists()
    with patch("subprocess.run") as run:
        run.return_value.stdout = ""
        reset_state(home, "docker")
    assert not home.exists()
    assert other.exists()


@pytest.mark.parametrize("part", ["home", "agent", "workspace"])
def test_symlinks_cannot_redirect_reset(tmp_path, part):
    home = state_home(tmp_path / "state", tmp_path, "hermes")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    target = {"home": home, "agent": home.parent, "workspace": home.parent.parent}[part]
    target.parent.mkdir(parents=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ConfigError, match="symlink"):
        reset_state(home, "docker")
    assert (outside / "keep").read_text() == "keep"


@pytest.mark.parametrize("state", [{"Running": True}, {"Paused": True}, {"Restarting": True}])
def test_active_container_prevents_reset(tmp_path, state):
    home = state_home(tmp_path, tmp_path, "hermes")
    home.mkdir(parents=True)
    with patch("subprocess.run") as run:
        run.return_value.stdout = "container-id"
        run.side_effect = [
            type("Result", (), {"stdout": "container-id"})(),
            type(
                "Result",
                (),
                {
                    "stdout": json.dumps(
                        [
                            {"State": state, "Mounts": [{"Source": str(home)}]},
                        ]
                    )
                },
            )(),
        ]
        with pytest.raises(ConfigError, match="active container"):
            reset_state(home, "docker")
    assert home.exists()


def test_unavailable_endpoint_refuses_reset(tmp_path):
    home = state_home(tmp_path, tmp_path, "hermes")
    home.mkdir(parents=True)
    with patch("subprocess.run", side_effect=OSError), pytest.raises(ConfigError, match="refused"):
        reset_state(home, "docker")
    assert home.exists()


def test_runtime_endpoint_is_preserved_for_reset(tmp_path, monkeypatch):
    home = state_home(tmp_path, tmp_path, "hermes")
    home.mkdir(parents=True)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/old.sock")
    record_runtime(home, "docker")
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/new.sock")
    with patch("subprocess.run") as run:
        run.return_value.stdout = ""
        reset_state(home, "docker")
    assert any(
        call.kwargs["env"].get("DOCKER_HOST") == "unix:///tmp/old.sock"
        for call in run.call_args_list
    )


def test_size_does_not_follow_symlinks(tmp_path):
    home = state_home(tmp_path / "state", tmp_path, "hermes")
    home.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "large").write_bytes(b"x" * 10000)
    (home / "link").symlink_to(outside, target_is_directory=True)
    (home / "small").write_text("abc")
    assert state_size(home) == 3


def test_cli_reset_requires_confirmation_and_show_hides_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agentbox.yaml").write_text(f"state_dir: {tmp_path / 'state'}")
    home = state_home(tmp_path / "state", tmp_path, "hermes")
    home.mkdir(parents=True)
    (home / "secret").write_text("never-print-this")
    result = CliRunner().invoke(main, ["state", "show", "--agent", "hermes"])
    assert result.exit_code == 0
    assert "never-print-this" not in result.output
    result = CliRunner().invoke(main, ["state", "reset", "--agent", "hermes"], input="n\n")
    assert result.exit_code != 0
    assert home.exists()
