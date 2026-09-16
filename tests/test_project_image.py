"""Project Dockerfile composition, caching and input validation."""

from unittest.mock import MagicMock

import pytest

from agentbox.config import Config
from agentbox.exceptions import ImageBuildError
from agentbox.image import ImageBuilder


def test_project_extension_uses_base_and_workspace_context(tmp_path):
    (tmp_path / "Dockerfile.agentbox").write_text("COPY dependency.txt /opt/dependency.txt\n")
    runtime = MagicMock()
    runtime.image_exists.return_value = True
    builder = ImageBuilder(runtime, Config(), workspace=tmp_path)
    image = builder.ensure_image()
    args, kwargs = runtime.build.call_args
    assert args[0].startswith("FROM agentbox:")
    assert "COPY dependency.txt" in args[0]
    assert args[1] == image
    assert kwargs == {"context": tmp_path}
    builder.ensure_image()
    assert runtime.build.call_count == 2  # Engine must recheck COPY inputs, even with cached image.


def test_project_hash_changes_with_instructions_and_base(tmp_path):
    path = tmp_path / "Dockerfile.agentbox"
    path.write_text("RUN true")
    builder = ImageBuilder(MagicMock(), Config(), workspace=tmp_path)
    first = builder.ensure_image()
    path.write_text("RUN echo changed")
    second = builder.ensure_image()
    builder.config.toolsets = ["kubernetes"]
    third = builder.ensure_image()
    assert len({first, second, third}) == 3


def test_force_rebuild_builds_base_and_project(tmp_path):
    (tmp_path / "Dockerfile.agentbox").write_text("RUN true")
    runtime = MagicMock()
    runtime.image_exists.return_value = True
    builder = ImageBuilder(runtime, Config(), workspace=tmp_path)
    builder.ensure_image(force_rebuild=True)
    assert runtime.build.call_count == 2
    assert not runtime.build.call_args_list[0].kwargs
    assert runtime.build.call_args_list[1].kwargs == {"context": tmp_path}


@pytest.mark.parametrize(
    "content", ["FROM alpine", "  from alpine\n", "RUN true\nFROM alpine AS other"]
)
def test_rejects_from_before_building(tmp_path, content):
    (tmp_path / "Dockerfile.agentbox").write_text(content)
    runtime = MagicMock()
    with pytest.raises(ImageBuildError, match="omit FROM"):
        ImageBuilder(runtime, Config(), workspace=tmp_path).ensure_image()
    runtime.build.assert_not_called()


def test_reports_unreadable_project_file(tmp_path):
    (tmp_path / "Dockerfile.agentbox").mkdir()
    with pytest.raises(ImageBuildError, match="Cannot read"):
        ImageBuilder(MagicMock(), Config(), workspace=tmp_path).ensure_image()


def test_only_workspace_root_is_checked(tmp_path):
    subdir = tmp_path / "nested"
    subdir.mkdir()
    (subdir / "Dockerfile.agentbox").write_text("RUN true")
    runtime = MagicMock()
    ImageBuilder(runtime, Config(), workspace=tmp_path).ensure_image()
    runtime.build.assert_not_called()


# This opt-in test exercises the engine cache, not just Dockerfile rendering.
@pytest.mark.parametrize("relative", ["Dockerfile.agentbox", "services/api/Dockerfile.agentbox"])
def test_real_project_copy_cache(tmp_path, monkeypatch, relative):
    import os
    import subprocess

    from agentbox.container import ContainerRuntime

    runtime_name = os.environ.get("AGENTBOX_PROJECT_TEST_RUNTIME")
    if runtime_name not in ("podman", "docker"):
        pytest.skip("Set AGENTBOX_PROJECT_TEST_RUNTIME=podman or docker")
    monkeypatch.chdir(tmp_path)
    selected = tmp_path / relative
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text("COPY dependency.txt /opt/dependency.txt\n")
    dependency = tmp_path / "dependency.txt"
    dependency.write_text("first")
    runtime = ContainerRuntime(runtime_name)
    builder = ImageBuilder(
        runtime,
        Config(toolsets=[], image_name="localhost/agentbox-project-test", project_dockerfile=relative),
        workspace=tmp_path,
    )
    first_image = builder.ensure_image()
    dependency.write_text("second")
    second_image = builder.ensure_image()
    assert second_image == first_image
    result = subprocess.run(
        [runtime_name, "run", "--rm", "--network=none", second_image, "cat", "/opt/dependency.txt"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert result.stdout == "second"


def test_selected_nested_dockerfile_uses_workspace_context(tmp_path):
    selected = tmp_path / "services/api/Dockerfile.agentbox"
    selected.parent.mkdir(parents=True)
    selected.write_text("COPY services/api/input.txt /opt/input.txt")
    runtime = MagicMock()
    builder = ImageBuilder(runtime, Config(project_dockerfile="services/api/Dockerfile.agentbox"), workspace=tmp_path)
    builder.ensure_image()
    assert runtime.build.call_args.kwargs["context"] == tmp_path


def test_selected_file_cannot_escape_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("RUN true")
    (workspace / "link").symlink_to(outside)
    for selected in ["../outside", str(outside), "link", "missing"]:
        runtime = MagicMock()
        with pytest.raises(ImageBuildError):
            ImageBuilder(runtime, Config(project_dockerfile=selected), workspace=workspace).ensure_image()
        runtime.build.assert_not_called()
