"""Tests for CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agentbox.cli import main
from agentbox.exceptions import RuntimeNotFoundError


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_runtime() -> MagicMock:
    """Create a mock container runtime."""
    with patch("agentbox.cli.ContainerRuntime") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_builder() -> MagicMock:
    """Create a mock image builder."""
    with patch("agentbox.cli.ImageBuilder") as mock:
        instance = MagicMock()
        instance.ensure_image.return_value = "agentbox:latest"
        mock.return_value = instance
        yield instance


class TestRunCommand:
    """Tests for the run command."""

    def test_run_with_default_workspace(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run command uses current directory as default workspace."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime") as mock_runtime_cls, \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_runtime = MagicMock()
            mock_runtime_cls.return_value = mock_runtime

            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            runner.invoke(main, ["run"])

            # Should have called run with current directory
            mock_runtime.run.assert_called_once()
            call_kwargs = mock_runtime.run.call_args
            assert call_kwargs[1]["workspace"] == tmp_path

    def test_run_creates_missing_workspace_on_confirm(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run command creates workspace directory when user confirms."""
        monkeypatch.chdir(tmp_path)
        new_workspace = tmp_path / "new-workspace"

        with patch("agentbox.cli.ContainerRuntime"), \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            runner.invoke(main, ["run", str(new_workspace)], input="y\n")

            assert new_workspace.exists()

    def test_run_aborts_on_missing_workspace_declined(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run command aborts when user declines to create workspace."""
        monkeypatch.chdir(tmp_path)
        new_workspace = tmp_path / "new-workspace"

        with patch("agentbox.cli.ContainerRuntime"), \
             patch("agentbox.cli.ImageBuilder"):
            result = runner.invoke(main, ["run", str(new_workspace)], input="n\n")

            assert result.exit_code == 1
            assert not new_workspace.exists()

    def test_run_bash_mode(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run with --bash flag uses bash command."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime") as mock_runtime_cls, \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_runtime = MagicMock()
            mock_runtime_cls.return_value = mock_runtime

            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            runner.invoke(main, ["run", "--bash"])

            mock_runtime.run.assert_called_once()
            call_kwargs = mock_runtime.run.call_args
            assert call_kwargs[1]["command"] == ["bash"]

    def test_run_with_read_only_mounts(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run with -r flag adds read-only mounts."""
        monkeypatch.chdir(tmp_path)

        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()

        with patch("agentbox.cli.ContainerRuntime") as mock_runtime_cls, \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_runtime = MagicMock()
            mock_runtime_cls.return_value = mock_runtime

            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            runner.invoke(main, ["run", "-r", str(ro_dir)])

            mock_runtime.run.assert_called_once()
            call_kwargs = mock_runtime.run.call_args
            assert ro_dir in call_kwargs[1]["ro_mounts"]

    def test_run_with_rebuild_flag(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run with --rebuild forces image rebuild."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime"), \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            runner.invoke(main, ["run", "--rebuild"])

            mock_builder.ensure_image.assert_called_once_with(force_rebuild=True)


class TestBuildCommand:
    """Tests for the build command."""

    def test_build_without_rebuild(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Build command without --rebuild flag."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime"), \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            result = runner.invoke(main, ["build"])

            mock_builder.ensure_image.assert_called_once_with(force_rebuild=False)
            assert result.exit_code == 0

    def test_build_with_rebuild(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Build command with --rebuild flag."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime"), \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            runner.invoke(main, ["build", "--rebuild"])

            mock_builder.ensure_image.assert_called_once_with(force_rebuild=True)


class TestConfigCommand:
    """Tests for the config command."""

    def test_config_shows_defaults(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config command shows default values when no config file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))

        result = runner.invoke(main, ["config"])

        assert result.exit_code == 0
        assert "podman" in result.output
        assert "agentbox" in result.output

    def test_config_shows_config_file_path(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config command shows config file path when present."""
        monkeypatch.chdir(tmp_path)

        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text("runtime: docker\n")

        result = runner.invoke(main, ["config"])

        assert result.exit_code == 0
        assert str(config_file) in result.output

    def test_config_show_subcommand(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config show subcommand works same as config."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))

        result = runner.invoke(main, ["config", "show"])

        assert result.exit_code == 0
        assert "podman" in result.output

    def test_config_init_creates_global_by_default(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config init creates global config by default."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = runner.invoke(main, ["config", "init"])

        assert result.exit_code == 0
        global_config = tmp_path / ".config" / "agentbox" / "config.yaml"
        assert global_config.exists()
        assert "Created global config" in result.output

    def test_config_init_global_flag(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config init --global creates global config."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = runner.invoke(main, ["config", "init", "--global"])

        assert result.exit_code == 0
        global_config = tmp_path / ".config" / "agentbox" / "config.yaml"
        assert global_config.exists()

    def test_config_init_project_flag(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config init --project creates project config."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(main, ["config", "init", "--project"])

        assert result.exit_code == 0
        project_config = tmp_path / ".agentbox.yaml"
        assert project_config.exists()
        assert "Created project config" in result.output

    def test_config_init_does_not_overwrite_without_force(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config init does not overwrite existing config without --force."""
        monkeypatch.chdir(tmp_path)

        # Create existing config
        project_config = tmp_path / ".agentbox.yaml"
        project_config.write_text("runtime: docker\n")

        result = runner.invoke(main, ["config", "init", "--project"])

        assert result.exit_code == 0
        assert "already exists" in result.output
        # Content should be unchanged
        assert project_config.read_text() == "runtime: docker\n"

    def test_config_init_force_overwrites(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config init --force overwrites existing config."""
        monkeypatch.chdir(tmp_path)

        # Create existing config
        project_config = tmp_path / ".agentbox.yaml"
        project_config.write_text("runtime: docker\n")

        result = runner.invoke(main, ["config", "init", "--project", "--force"])

        assert result.exit_code == 0
        assert "Created project config" in result.output
        # Content should be new default
        assert "runtime: docker\n" not in project_config.read_text()


class TestToolsetCommand:
    """Tests for the toolset command."""

    def test_toolset_shows_details(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Toolset command shows toolset details."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(main, ["toolset", "base"])

        assert result.exit_code == 0
        assert "base" in result.output
        assert "Origin:" in result.output
        assert "Priority:" in result.output

    def test_toolset_not_found_error(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Toolset command shows error for unknown toolset."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(main, ["toolset", "nonexistent-toolset"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_toolset_shows_mounts(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Toolset command shows mount information."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(main, ["toolset", "cloud-aws"])

        assert result.exit_code == 0
        assert "Mounts:" in result.output
        assert "~/.aws" in result.output


class TestSafeCommandsWithInvalidConfig:
    """Tests for commands that can run with invalid config."""

    def test_config_command_works_with_invalid_config(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config command succeeds even with invalid config file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        # Create invalid config
        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text("claude: null\n")

        result = runner.invoke(main, ["config"])

        assert result.exit_code == 0
        assert "Warning: Invalid config file" in result.output
        assert "agentbox config init --force" in result.output

    def test_config_init_works_with_invalid_config(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config init --force can fix invalid config file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        # Create invalid config
        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text("claude: null\n")

        result = runner.invoke(main, ["config", "init", "--project", "--force"])

        assert result.exit_code == 0
        assert "Created project config" in result.output

        # Config should now be valid
        new_content = config_file.read_text()
        assert "claude: null" not in new_content

    def test_run_command_fails_with_invalid_config(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run command fails with helpful error on invalid config."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        # Create invalid config
        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text("claude: null\n")

        result = runner.invoke(main, ["run"])

        assert result.exit_code != 0
        assert result.exception is not None

    def test_upgrade_command_works_with_invalid_config(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade command succeeds even with invalid config file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))

        # Create invalid config
        config_file = tmp_path / ".agentbox.yaml"
        config_file.write_text("claude: null\n")

        result = runner.invoke(main, ["upgrade"])

        # Should succeed (shows instructions for non-venv install)
        assert result.exit_code == 0


class TestUpgradeCommand:
    """Tests for the upgrade command."""

    def test_upgrade_shows_instructions_for_non_venv_install(
        self,
        runner: CliRunner,
    ) -> None:
        """Upgrade command shows instructions when not installed via install.sh."""
        result = runner.invoke(main, ["upgrade"])

        # When not in ~/.agentbox/venv, should show instructions
        assert result.exit_code == 0
        assert "not installed via install.sh" in result.output or "pipx" in result.output

    def test_upgrade_runs_pip_when_in_venv(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade command runs pip when installed via install.sh."""
        # Create fake venv structure
        venv_path = tmp_path / ".agentbox" / "venv"
        venv_bin = venv_path / "bin"
        venv_bin.mkdir(parents=True)
        fake_pip = venv_bin / "pip"
        fake_pip.touch()

        # Mock sys.executable to be inside the venv
        fake_python = venv_bin / "python"
        monkeypatch.setattr("sys.executable", str(fake_python))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = runner.invoke(main, ["upgrade"])

            assert result.exit_code == 0
            assert "upgraded successfully" in result.output
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "pip" in call_args[0]
            assert "--force-reinstall" in call_args

    def test_upgrade_shows_error_on_pip_failure(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade command shows both stdout and stderr on pip failure."""
        # Create fake venv structure
        venv_path = tmp_path / ".agentbox" / "venv"
        venv_bin = venv_path / "bin"
        venv_bin.mkdir(parents=True)
        fake_pip = venv_bin / "pip"
        fake_pip.touch()

        # Mock sys.executable to be inside the venv
        fake_python = venv_bin / "python"
        monkeypatch.setattr("sys.executable", str(fake_python))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="Some stdout error",
                stderr="Some stderr error",
            )

            result = runner.invoke(main, ["upgrade"])

            assert result.exit_code == 1
            assert "Error upgrading" in result.output
            assert "Some stdout error" in result.output
            assert "Some stderr error" in result.output

    def test_upgrade_handles_missing_pip(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Upgrade command handles missing pip gracefully."""
        # Create fake venv structure without pip
        venv_path = tmp_path / ".agentbox" / "venv"
        venv_bin = venv_path / "bin"
        venv_bin.mkdir(parents=True)

        # Mock sys.executable to be inside the venv
        fake_python = venv_bin / "python"
        monkeypatch.setattr("sys.executable", str(fake_python))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pip not found")

            result = runner.invoke(main, ["upgrade"])

            assert result.exit_code == 1
            assert "pip not found" in result.output


class TestErrorHandling:
    """Tests for CLI error handling."""

    def test_runtime_not_found_error(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RuntimeNotFoundError propagates from ContainerRuntime."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime") as mock_cls:
            mock_cls.side_effect = RuntimeNotFoundError("podman")

            result = runner.invoke(main, ["run"])

            # Exception should be raised (not caught by CliRunner by default)
            assert result.exception is not None
            assert isinstance(result.exception, RuntimeNotFoundError)

    def test_unknown_agent_error(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unknown agent shows friendly error."""
        monkeypatch.chdir(tmp_path)

        with patch("agentbox.cli.ContainerRuntime"), \
             patch("agentbox.cli.ImageBuilder") as mock_builder_cls:
            mock_builder = MagicMock()
            mock_builder.ensure_image.return_value = "agentbox"
            mock_builder_cls.return_value = mock_builder

            result = runner.invoke(main, ["run", "--agent", "nonexistent"])

            assert result.exit_code != 0
            assert result.exception is not None


class TestMainHelp:
    """Tests for main command help."""

    def test_main_without_subcommand_shows_help(self, runner: CliRunner) -> None:
        """Main command without subcommand shows help."""
        result = runner.invoke(main)

        assert result.exit_code == 0
        assert "run" in result.output
        assert "build" in result.output
        assert "config" in result.output

    def test_version_option(self, runner: CliRunner) -> None:
        """--version shows version."""
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "agentbox" in result.output.lower()
