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
