"""Prebuilt selection and project extension identity."""

from unittest.mock import MagicMock

import pytest

from agentbox.config import Config
from agentbox.exceptions import ImageBuildError
from agentbox.image import ImageBuilder


def test_prebuilt_pull_only_when_missing_or_refreshing(tmp_path):
    runtime = MagicMock()
    runtime.image_exists.return_value = False
    builder = ImageBuilder(runtime, Config(prebuilt_image='ghcr.io/example/image:base'), workspace=tmp_path)
    assert builder.ensure_image() == 'ghcr.io/example/image:base'
    runtime.pull.assert_called_once_with('ghcr.io/example/image:base')
    runtime.build.assert_not_called()
    runtime.image_exists.return_value = True
    builder.ensure_image()
    assert runtime.pull.call_count == 1
    builder.ensure_image(force_rebuild=True)
    assert runtime.pull.call_count == 2


def test_digest_reference_can_be_extended_without_invalid_local_tag(tmp_path):
    (tmp_path / 'Dockerfile.agentbox').write_text('RUN true')
    runtime = MagicMock()
    runtime.image_id.return_value = 'sha256:' + 'a' * 64
    config = Config(prebuilt_image='ghcr.io/example/image@sha256:' + 'b' * 64)
    builder = ImageBuilder(runtime, config, workspace=tmp_path)
    first = builder.ensure_image()
    assert first.startswith('agentbox:')
    assert runtime.build.call_args.args[0].startswith('FROM ghcr.io/example/image@sha256:')
    runtime.image_id.return_value = 'sha256:' + 'c' * 64
    assert builder.ensure_image() != first


@pytest.mark.parametrize('image', ['', '--help', 'image\nRUN evil', 'image name'])
def test_invalid_reference_rejected_before_engine_calls(tmp_path, image):
    runtime = MagicMock()
    with pytest.raises(ImageBuildError, match='Invalid prebuilt'):
        ImageBuilder(runtime, Config(prebuilt_image=image), workspace=tmp_path).ensure_image()
    runtime.pull.assert_not_called()
    runtime.build.assert_not_called()


@pytest.mark.parametrize('command', ['build', 'run'])
def test_cli_image_override(tmp_path, monkeypatch, command):
    from click.testing import CliRunner
    from agentbox.cli import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('agentbox.cli.ContainerRuntime', MagicMock())
    builder = MagicMock()
    builder.return_value.ensure_image.return_value = 'example:base'
    monkeypatch.setattr('agentbox.cli.ImageBuilder', builder)
    result = CliRunner().invoke(main, [command, '--image', 'example:base'])
    assert result.exit_code == 0, result.output
    assert builder.call_args.args[1].prebuilt_image == 'example:base'
