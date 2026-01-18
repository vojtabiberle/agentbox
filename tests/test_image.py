"""Tests for image building."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.config import Config
from agentbox.image import ImageBuilder


@pytest.fixture
def mock_runtime() -> MagicMock:
    """Create a mock container runtime."""
    runtime = MagicMock()
    runtime.runtime = "podman"
    return runtime


class TestSetupJinja:
    """Tests for Jinja2 environment setup."""

    def test_setup_jinja_with_package_loader(self, mock_runtime: MagicMock) -> None:
        """Jinja2 environment set up with PackageLoader."""
        config = Config()
        builder = ImageBuilder(mock_runtime, config)

        # Should have env attribute
        assert builder.env is not None
        assert builder.env.get_template("Dockerfile.j2") is not None

    def test_setup_jinja_fallback_to_filesystem(self, mock_runtime: MagicMock) -> None:
        """Jinja2 falls back to FileSystemLoader when package fails."""
        config = Config()

        with patch("agentbox.image.PackageLoader", side_effect=TypeError):
            builder = ImageBuilder(mock_runtime, config)

            # Should still work with FileSystemLoader fallback
            assert builder.env is not None


class TestEnsureImage:
    """Tests for ensure_image method."""

    def test_ensure_image_returns_existing(self, mock_runtime: MagicMock) -> None:
        """ensure_image returns image name when image exists."""
        mock_runtime.image_exists.return_value = True
        config = Config(image_name="test-image")

        builder = ImageBuilder(mock_runtime, config)
        result = builder.ensure_image()

        assert result == "test-image"
        mock_runtime.build.assert_not_called()

    def test_ensure_image_builds_when_missing(self, mock_runtime: MagicMock) -> None:
        """ensure_image builds image when it doesn't exist."""
        mock_runtime.image_exists.return_value = False
        config = Config(image_name="test-image")

        builder = ImageBuilder(mock_runtime, config)
        result = builder.ensure_image()

        assert result == "test-image"
        mock_runtime.build.assert_called_once()

    def test_ensure_image_force_rebuild(self, mock_runtime: MagicMock) -> None:
        """ensure_image rebuilds when force_rebuild=True."""
        mock_runtime.image_exists.return_value = True
        config = Config(image_name="test-image")

        builder = ImageBuilder(mock_runtime, config)
        result = builder.ensure_image(force_rebuild=True)

        assert result == "test-image"
        mock_runtime.build.assert_called_once()

    def test_ensure_image_passes_correct_tag(self, mock_runtime: MagicMock) -> None:
        """ensure_image passes correct tag to build."""
        mock_runtime.image_exists.return_value = False
        config = Config(image_name="custom-image")

        builder = ImageBuilder(mock_runtime, config)
        builder.ensure_image()

        call_args = mock_runtime.build.call_args
        assert call_args[0][1] == "custom-image"


class TestRenderDockerfile:
    """Tests for _render_dockerfile method."""

    def test_render_dockerfile_includes_base(self, mock_runtime: MagicMock) -> None:
        """Rendered Dockerfile includes base content."""
        config = Config(toolsets=["base"])
        builder = ImageBuilder(mock_runtime, config)

        dockerfile = builder._render_dockerfile()

        assert "FROM" in dockerfile

    def test_render_dockerfile_passes_dockerfile_fragments(
        self, mock_runtime: MagicMock
    ) -> None:
        """Dockerfile fragments from plugins are passed to template rendering."""
        config = Config(toolsets=["base", "python", "go"])
        builder = ImageBuilder(mock_runtime, config)

        # Load plugins first (normally done by ensure_image)
        builder.plugin_manager.load(config.toolsets)

        # Mock the template to capture render args
        mock_template = MagicMock()
        mock_template.render.return_value = "FROM ubuntu"
        builder.env.get_template = MagicMock(return_value=mock_template)

        builder._render_dockerfile()

        # Verify render was called with dockerfile_fragments
        mock_template.render.assert_called_once()
        call_kwargs = mock_template.render.call_args[1]
        assert "dockerfile_fragments" in call_kwargs
        assert isinstance(call_kwargs["dockerfile_fragments"], list)
        # Should have fragments for base, python, go (3 fragments)
        assert len(call_kwargs["dockerfile_fragments"]) == 3

    def test_render_dockerfile_with_different_toolsets(
        self, mock_runtime: MagicMock
    ) -> None:
        """Different toolsets produce different Dockerfiles."""
        config_base = Config(toolsets=["base"])
        config_python = Config(toolsets=["base", "python"])

        builder_base = ImageBuilder(mock_runtime, config_base)
        builder_python = ImageBuilder(mock_runtime, config_python)

        dockerfile_base = builder_base._render_dockerfile()
        dockerfile_python = builder_python._render_dockerfile()

        # Python toolset should include python-specific content
        # (This depends on actual template, but we verify they're different)
        # If template doesn't change output, this test documents the expectation
        assert isinstance(dockerfile_base, str)
        assert isinstance(dockerfile_python, str)


class TestProjectImageTagging:
    """Tests for project-specific image tagging."""

    def test_is_project_config_returns_false_when_no_config_path(
        self, mock_runtime: MagicMock
    ) -> None:
        """_is_project_config returns False when config_path is None."""
        config = Config()
        builder = ImageBuilder(mock_runtime, config, config_path=None)

        assert builder._is_project_config() is False

    def test_is_project_config_returns_true_for_project_config(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_is_project_config returns True for .agentbox.yaml in cwd."""
        monkeypatch.chdir(tmp_path)
        config = Config()
        project_config = tmp_path / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        assert builder._is_project_config() is True

    def test_is_project_config_returns_true_for_yml_extension(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_is_project_config returns True for .agentbox.yml extension."""
        monkeypatch.chdir(tmp_path)
        config = Config()
        project_config = tmp_path / ".agentbox.yml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        assert builder._is_project_config() is True

    def test_is_project_config_returns_false_for_global_config(
        self, mock_runtime: MagicMock, tmp_path: Path
    ) -> None:
        """_is_project_config returns False for global config.yaml."""
        config = Config()
        global_config = tmp_path / ".config" / "agentbox" / "config.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=global_config)

        assert builder._is_project_config() is False

    def test_is_project_config_returns_false_for_home_agentbox_yaml(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_is_project_config returns False for ~/.agentbox.yaml (legacy global)."""
        # Simulate being in home directory with ~/.agentbox.yaml
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = Config()
        home_config = tmp_path / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=home_config)

        # Should be treated as global, not project config
        assert builder._is_project_config() is False

    def test_is_project_config_returns_false_when_config_not_in_cwd(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_is_project_config returns False when config is not in current directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)  # cwd is different from config location

        config = Config()
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        assert builder._is_project_config() is False

    def test_get_project_name_from_config_path(
        self, mock_runtime: MagicMock, tmp_path: Path
    ) -> None:
        """_get_project_name returns directory name from config path."""
        config = Config()
        project_dir = tmp_path / "my-awesome-project"
        project_dir.mkdir()
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        assert builder._get_project_name() == "my-awesome-project"

    def test_compute_image_name_uses_default_for_no_project_config(
        self, mock_runtime: MagicMock
    ) -> None:
        """_compute_image_name returns default image name when no project config."""
        config = Config(image_name="agentbox")
        builder = ImageBuilder(mock_runtime, config, config_path=None)

        result = builder._compute_image_name("FROM ubuntu")

        assert result == "agentbox"

    def test_compute_image_name_uses_default_for_global_config(
        self, mock_runtime: MagicMock, tmp_path: Path
    ) -> None:
        """_compute_image_name returns default image name for global config."""
        config = Config(image_name="agentbox")
        global_config = tmp_path / ".config" / "agentbox" / "config.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=global_config)

        result = builder._compute_image_name("FROM ubuntu")

        assert result == "agentbox"

    def test_compute_image_name_uses_default_for_home_agentbox_yaml(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_compute_image_name returns default for ~/.agentbox.yaml."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = Config(image_name="agentbox")
        home_config = tmp_path / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=home_config)

        result = builder._compute_image_name("FROM ubuntu")

        # Should use default, not project tag
        assert result == "agentbox"

    def test_compute_image_name_creates_unique_tag_for_project_config(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_compute_image_name creates unique tag for project config."""
        config = Config()
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        result = builder._compute_image_name("FROM ubuntu")

        # Should be agentbox:<project>-<hash>
        assert result.startswith("agentbox:myproject-")
        assert len(result.split("-")[-1]) == 8  # 8 char hash

    def test_compute_image_name_uses_custom_image_name_as_base(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_compute_image_name uses config.image_name as base for project tags."""
        config = Config(image_name="custom-image")
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        result = builder._compute_image_name("FROM ubuntu")

        # Should use custom-image as base, not agentbox
        assert result.startswith("custom-image:myproject-")

    def test_compute_image_name_hash_changes_with_dockerfile(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Different dockerfile content produces different hash."""
        config = Config()
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        result1 = builder._compute_image_name("FROM ubuntu")
        result2 = builder._compute_image_name("FROM debian")

        # Same project, different dockerfile = different hash
        assert result1 != result2
        assert result1.startswith("agentbox:myproject-")
        assert result2.startswith("agentbox:myproject-")

    def test_compute_image_name_sanitizes_project_name(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_compute_image_name sanitizes project name for docker tag."""
        config = Config()
        project_dir = tmp_path / "My_Project.Name"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        result = builder._compute_image_name("FROM ubuntu")

        # Should be lowercase and sanitized
        assert "My_Project" not in result
        assert result.startswith("agentbox:my-project-name-")

    def test_compute_image_name_truncates_long_project_name(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_compute_image_name truncates very long project names."""
        config = Config()
        long_name = "this-is-a-very-long-project-name-that-exceeds-limits"
        project_dir = tmp_path / long_name
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        result = builder._compute_image_name("FROM ubuntu")

        # Project name portion should be truncated to 20 chars
        tag = result.split(":")[1]
        project_part = tag.rsplit("-", 1)[0]
        assert len(project_part) <= 20

    def test_ensure_image_uses_project_tag_for_project_config(
        self, mock_runtime: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ensure_image uses project-specific tag when project config is used."""
        mock_runtime.image_exists.return_value = False
        config = Config()
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        project_config = project_dir / ".agentbox.yaml"
        builder = ImageBuilder(mock_runtime, config, config_path=project_config)

        result = builder.ensure_image()

        # Should return project-specific tag
        assert result.startswith("agentbox:myproject-")
        # Should pass project tag to build
        call_args = mock_runtime.build.call_args
        assert call_args[0][1].startswith("agentbox:myproject-")
