"""Tests for container runtime abstraction."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.container import ContainerRuntime
from agentbox.config import Config
from agentbox.exceptions import RuntimeNotFoundError


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
