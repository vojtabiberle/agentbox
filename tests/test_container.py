"""Tests for container runtime abstraction."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.exceptions import RuntimeNotFoundError
from agentbox.git import GitWorktreeInfo


class TestVerifyRuntime:
    """Tests for _verify_runtime method."""

    def test_raises_when_binary_missing(self) -> None:
        """RuntimeNotFoundError raised when binary not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeNotFoundError) as exc_info:
                ContainerRuntime("podman")
            assert "podman" in str(exc_info.value)

    def test_raises_when_binary_fails(self) -> None:
        """RuntimeNotFoundError raised when binary exists but fails."""
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "podman")):
            with pytest.raises(RuntimeNotFoundError):
                ContainerRuntime("podman")

    def test_succeeds_when_binary_works(self) -> None:
        """Runtime created successfully when binary works."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            runtime = ContainerRuntime("podman")
            assert runtime.runtime == "podman"


class TestImageExists:
    """Tests for image_exists method."""

    @pytest.fixture
    def runtime_podman(self) -> ContainerRuntime:
        """Create a podman runtime with mocked verification."""
        with patch("subprocess.run"):
            return ContainerRuntime("podman")

    @pytest.fixture
    def runtime_docker(self) -> ContainerRuntime:
        """Create a docker runtime with mocked verification."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_podman_uses_image_exists(self, runtime_podman: ContainerRuntime) -> None:
        """Podman uses 'image exists' command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runtime_podman.image_exists("test-image")

            assert result is True
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == ["podman", "image", "exists", "test-image"]

    def test_docker_uses_image_inspect(self, runtime_docker: ContainerRuntime) -> None:
        """Docker uses 'image inspect' command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runtime_docker.image_exists("test-image")

            assert result is True
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == ["docker", "image", "inspect", "test-image"]

    def test_returns_false_when_image_missing(self, runtime_podman: ContainerRuntime) -> None:
        """Returns False when image does not exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = runtime_podman.image_exists("nonexistent")
            assert result is False


class TestVolSuffix:
    """Tests for _vol_suffix method."""

    @pytest.fixture
    def runtime_podman(self) -> ContainerRuntime:
        """Create a podman runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("podman")

    @pytest.fixture
    def runtime_docker(self) -> ContainerRuntime:
        """Create a docker runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_podman_default_suffix(self, runtime_podman: ContainerRuntime) -> None:
        """Podman adds :Z for SELinux."""
        assert runtime_podman._vol_suffix() == ":Z"

    def test_podman_ro_suffix(self, runtime_podman: ContainerRuntime) -> None:
        """Podman adds :ro,Z for read-only."""
        assert runtime_podman._vol_suffix("ro") == ":ro,Z"

    def test_podman_rw_suffix(self, runtime_podman: ContainerRuntime) -> None:
        """Podman adds :rw,Z for read-write."""
        assert runtime_podman._vol_suffix("rw") == ":rw,Z"

    def test_docker_default_suffix(self, runtime_docker: ContainerRuntime) -> None:
        """Docker has no default suffix."""
        assert runtime_docker._vol_suffix() == ""

    def test_docker_ro_suffix(self, runtime_docker: ContainerRuntime) -> None:
        """Docker adds :ro for read-only."""
        assert runtime_docker._vol_suffix("ro") == ":ro"

    def test_docker_rw_suffix(self, runtime_docker: ContainerRuntime) -> None:
        """Docker adds :rw for read-write."""
        assert runtime_docker._vol_suffix("rw") == ":rw"


class TestAddCredentialMounts:
    """Tests for _add_credential_mounts method."""

    @pytest.fixture
    def runtime(self) -> ContainerRuntime:
        """Create a docker runtime for simpler assertions."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_github_mount_when_enabled_and_exists(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GitHub credentials mounted when enabled and directory exists."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        gh_config = tmp_path / ".config" / "gh"
        gh_config.mkdir(parents=True)

        config = Config.model_validate({"credentials": {"github": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert any(".config/gh" in c for c in cmd)

    def test_github_mount_skipped_when_dir_missing(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GitHub credentials not mounted when directory missing."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        config = Config.model_validate({"credentials": {"github": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert not any(".config/gh" in c for c in cmd)

    def test_github_mount_skipped_when_disabled(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GitHub credentials not mounted when disabled."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        gh_config = tmp_path / ".config" / "gh"
        gh_config.mkdir(parents=True)

        config = Config.model_validate({"credentials": {"github": False}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert not any(".config/gh" in c for c in cmd)

    def test_aws_mount_when_enabled(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AWS credentials mounted when enabled."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        aws_dir = tmp_path / ".aws"
        aws_dir.mkdir()

        config = Config.model_validate({"credentials": {"aws": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert any(".aws" in c for c in cmd)

    def test_azure_mount_when_enabled(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Azure credentials mounted when enabled."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        azure_dir = tmp_path / ".azure"
        azure_dir.mkdir()

        config = Config.model_validate({"credentials": {"azure": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert any(".azure" in c for c in cmd)

    def test_gcloud_mount_when_enabled(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GCloud credentials mounted when enabled."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        gcloud_dir = tmp_path / ".config" / "gcloud"
        gcloud_dir.mkdir(parents=True)

        config = Config.model_validate({"credentials": {"gcloud": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert any(".config/gcloud" in c for c in cmd)

    def test_ssh_agent_mount_when_enabled(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SSH agent socket mounted when enabled and available."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Create a fake socket file
        ssh_sock = tmp_path / "ssh-agent.sock"
        ssh_sock.touch()
        monkeypatch.setenv("SSH_AUTH_SOCK", str(ssh_sock))

        config = Config.model_validate({"credentials": {"ssh_agent": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert any("ssh-agent.sock" in c for c in cmd)
        assert any("SSH_AUTH_SOCK" in c for c in cmd)

    def test_ssh_agent_skipped_when_sock_missing(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SSH agent not mounted when socket doesn't exist."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("SSH_AUTH_SOCK", "/nonexistent/socket")

        config = Config.model_validate({"credentials": {"ssh_agent": True}})
        cmd: list[str] = []
        runtime._add_credential_mounts(cmd, config)

        assert not any("SSH_AUTH_SOCK" in c for c in cmd)


class TestAddClaudeMounts:
    """Tests for _add_claude_mounts method."""

    @pytest.fixture
    def runtime(self) -> ContainerRuntime:
        """Create a docker runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_claude_dir_mounted_when_exists(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.claude directory mounted when it exists."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        config = Config()
        cmd: list[str] = []
        runtime._add_claude_mounts(cmd, config)

        assert any(".claude" in c and ".claude.json" not in c for c in cmd)

    def test_claude_json_mounted_when_exists(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """~/.claude.json file mounted when it exists."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        claude_json = tmp_path / ".claude.json"
        claude_json.touch()

        config = Config()
        cmd: list[str] = []
        runtime._add_claude_mounts(cmd, config)

        assert any(".claude.json" in c for c in cmd)

    def test_global_claude_md_mounted_when_configured(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Global CLAUDE.md mounted when configured and exists."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        claude_md = tmp_path / "CLAUDE.md"
        claude_md.touch()

        config = Config.model_validate({"claude": {"global_claude_md": str(claude_md)}})
        cmd: list[str] = []
        runtime._add_claude_mounts(cmd, config)

        assert any("CLAUDE.md" in c for c in cmd)

    def test_plugins_dir_mounted_when_configured(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plugins directory mounted when configured and exists."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        config = Config.model_validate({"claude": {"plugins_dir": str(plugins_dir)}})
        cmd: list[str] = []
        runtime._add_claude_mounts(cmd, config)

        assert any("plugins" in c for c in cmd)


class TestGetTerminalSize:
    """Tests for _get_terminal_columns and _get_terminal_lines."""

    @pytest.fixture
    def runtime(self) -> ContainerRuntime:
        """Create a docker runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_columns_from_env(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """COLUMNS env var takes priority over OS detection."""
        monkeypatch.setenv("COLUMNS", "200")
        assert runtime._get_terminal_columns() == "200"

    def test_lines_from_env(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LINES env var takes priority over OS detection."""
        monkeypatch.setenv("LINES", "50")
        assert runtime._get_terminal_lines() == "50"

    def test_columns_from_os_when_no_env(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to os.get_terminal_size() when COLUMNS not set."""
        monkeypatch.delenv("COLUMNS", raising=False)
        with patch("os.get_terminal_size", return_value=os.terminal_size((120, 40))):
            assert runtime._get_terminal_columns() == "120"

    def test_lines_from_os_when_no_env(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to os.get_terminal_size() when LINES not set."""
        monkeypatch.delenv("LINES", raising=False)
        with patch("os.get_terminal_size", return_value=os.terminal_size((120, 40))):
            assert runtime._get_terminal_lines() == "40"

    def test_columns_fallback_on_oserror(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to 80 when both env and OS detection fail."""
        monkeypatch.delenv("COLUMNS", raising=False)
        with patch("os.get_terminal_size", side_effect=OSError):
            assert runtime._get_terminal_columns() == "80"

    def test_lines_fallback_on_oserror(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to 24 when both env and OS detection fail."""
        monkeypatch.delenv("LINES", raising=False)
        with patch("os.get_terminal_size", side_effect=OSError):
            assert runtime._get_terminal_lines() == "24"

    def test_columns_fallback_on_value_error(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to 80 on ValueError from os.get_terminal_size()."""
        monkeypatch.delenv("COLUMNS", raising=False)
        with patch("os.get_terminal_size", side_effect=ValueError):
            assert runtime._get_terminal_columns() == "80"

    def test_lines_fallback_on_value_error(
        self, runtime: ContainerRuntime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to 24 on ValueError from os.get_terminal_size()."""
        monkeypatch.delenv("LINES", raising=False)
        with patch("os.get_terminal_size", side_effect=ValueError):
            assert runtime._get_terminal_lines() == "24"


class TestRunTerminalSize:
    """Tests for terminal size propagation in run()."""

    @pytest.fixture
    def runtime(self) -> ContainerRuntime:
        """Create a docker runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_run_passes_columns_and_lines(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() includes COLUMNS and LINES env vars in the command."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("COLUMNS", "160")
        monkeypatch.setenv("LINES", "48")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        config = Config()

        with patch("os.execvp") as mock_exec:
            runtime.run(
                image="agentbox",
                workspace=workspace,
                ro_mounts=[],
                command=["bash"],
                config=config,
            )

            cmd = mock_exec.call_args[0][1]
            # Find COLUMNS and LINES in the -e arguments
            env_args = [cmd[i + 1] for i in range(len(cmd) - 1) if cmd[i] == "-e"]
            assert "COLUMNS=160" in env_args
            assert "LINES=48" in env_args

    def test_run_uses_fallback_terminal_size(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() uses fallback values when no TTY and no env vars."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("COLUMNS", raising=False)
        monkeypatch.delenv("LINES", raising=False)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        config = Config()

        with (
            patch("os.execvp") as mock_exec,
            patch("os.get_terminal_size", side_effect=OSError),
        ):
            runtime.run(
                image="agentbox",
                workspace=workspace,
                ro_mounts=[],
                command=["bash"],
                config=config,
            )

            cmd = mock_exec.call_args[0][1]
            env_args = [cmd[i + 1] for i in range(len(cmd) - 1) if cmd[i] == "-e"]
            assert "COLUMNS=80" in env_args
            assert "LINES=24" in env_args


class TestRun:
    """Tests for run method."""

    @pytest.fixture
    def runtime(self) -> ContainerRuntime:
        """Create a docker runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_run_constructs_correct_command(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run constructs correct docker/podman command."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        config = Config()

        with patch("os.execvp") as mock_exec:
            runtime.run(
                image="agentbox",
                workspace=workspace,
                ro_mounts=[],
                command=["bash"],
                config=config,
            )

            mock_exec.assert_called_once()
            cmd = mock_exec.call_args[0][1]

            assert cmd[0] == "docker"
            assert "run" in cmd
            assert "-it" in cmd
            assert "--rm" in cmd
            assert "agentbox" in cmd
            assert "bash" in cmd

    def test_run_includes_ro_mounts(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run includes read-only mounts."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()

        config = Config()

        with patch("os.execvp") as mock_exec:
            runtime.run(
                image="agentbox",
                workspace=workspace,
                ro_mounts=[ro_dir],
                command=["bash"],
                config=config,
            )

            cmd = mock_exec.call_args[0][1]
            cmd_str = " ".join(cmd)
            assert "/mnt/ro0" in cmd_str


class TestAddGitMounts:
    """Tests for _add_git_mounts method."""

    @pytest.fixture
    def runtime(self) -> ContainerRuntime:
        """Create a docker runtime."""
        with patch("subprocess.run"):
            return ContainerRuntime("docker")

    def test_no_git_worktree_no_mount(self, runtime: ContainerRuntime) -> None:
        """No git mounts when git_worktree is None."""
        cmd: list[str] = []
        runtime._add_git_mounts(cmd, None)
        assert cmd == []

    def test_needs_mount_false_no_mount(self, runtime: ContainerRuntime) -> None:
        """No git mounts when needs_mount is False."""
        info = GitWorktreeInfo(
            git_common_dir=Path("/repo/.git"),
            git_dir=Path("/repo/.git"),
            needs_mount=False,
        )
        cmd: list[str] = []
        runtime._add_git_mounts(cmd, info)
        assert cmd == []

    def test_worktree_mounts_common_dir(self, runtime: ContainerRuntime) -> None:
        """Worktree mounts git_common_dir at same path with rw."""
        info = GitWorktreeInfo(
            git_common_dir=Path("/home/user/main-repo/.git"),
            git_dir=Path("/home/user/main-repo/.git/worktrees/wt"),
            needs_mount=True,
        )
        cmd: list[str] = []
        runtime._add_git_mounts(cmd, info)

        assert "-v" in cmd
        cmd_str = " ".join(cmd)
        assert "/home/user/main-repo/.git:/home/user/main-repo/.git:rw" in cmd_str
        # git_dir is under common_dir, so only one mount
        assert cmd.count("-v") == 1

    def test_git_dir_not_under_common_dir_both_mounted(self, runtime: ContainerRuntime) -> None:
        """Both common_dir and git_dir mounted when git_dir is outside common_dir."""
        info = GitWorktreeInfo(
            git_common_dir=Path("/home/user/main-repo/.git"),
            git_dir=Path("/somewhere/else/.git-dir"),
            needs_mount=True,
        )
        cmd: list[str] = []
        runtime._add_git_mounts(cmd, info)

        assert cmd.count("-v") == 2
        cmd_str = " ".join(cmd)
        assert "/home/user/main-repo/.git:/home/user/main-repo/.git:rw" in cmd_str
        assert "/somewhere/else/.git-dir:/somewhere/else/.git-dir:rw" in cmd_str

    def test_run_passes_git_worktree(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() passes git_worktree to _add_git_mounts."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        info = GitWorktreeInfo(
            git_common_dir=Path("/main/.git"),
            git_dir=Path("/main/.git/worktrees/wt"),
            needs_mount=True,
        )
        config = Config()

        with patch("os.execvp") as mock_exec:
            runtime.run(
                image="agentbox",
                workspace=workspace,
                ro_mounts=[],
                command=["bash"],
                config=config,
                git_worktree=info,
            )

            cmd = mock_exec.call_args[0][1]
            cmd_str = " ".join(cmd)
            assert "/main/.git:/main/.git:rw" in cmd_str

    def test_run_without_git_worktree(
        self, runtime: ContainerRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() works normally when git_worktree is None."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        config = Config()

        with patch("os.execvp") as mock_exec:
            runtime.run(
                image="agentbox",
                workspace=workspace,
                ro_mounts=[],
                command=["bash"],
                config=config,
                git_worktree=None,
            )

            cmd = mock_exec.call_args[0][1]
            cmd_str = " ".join(cmd)
            # No git-specific mount should appear
            assert cmd_str.count("/.git") == 0 or all(
                ".claude" in part for part in cmd_str.split() if "/.git" in part
            )
