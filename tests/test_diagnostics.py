import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from agentbox.cli import main
from agentbox.config import Config
from agentbox.execution import prepare_run
from agentbox.image import ImageBuilder


def test_preview_creates_no_home_and_redacts_values(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'host')
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-env-sentinel')
    monkeypatch.setattr('agentbox.cli.ContainerRuntime', MagicMock())
    (tmp_path / '.agentbox.yaml').write_text('toolsets: [base]\n')
    result = CliRunner().invoke(main, ['run', str(tmp_path), '--dry-run', '--env', 'OPENAI_API_KEY', '--', 'secret-command-sentinel'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert 'OPENAI_API_KEY' in data['environment_names']
    assert 'secret-' not in result.output
    assert not (tmp_path / 'host').exists()
    assert data['mounts'][0]['readonly'] is False


def test_preview_does_not_call_engine_even_with_rebuild_and_project(tmp_path):
    (tmp_path / 'Dockerfile.agentbox').write_text('RUN true')
    runtime = MagicMock()
    builder = ImageBuilder(runtime, Config(prebuilt_image='example:base'), workspace=tmp_path)
    assert builder.ensure_image(force_rebuild=True, dry_run=True) == 'example:base'
    assert not runtime.mock_calls


def test_preview_missing_external_mount_still_fails(tmp_path):
    from agentbox.exceptions import ConfigError
    with pytest.raises(ConfigError, match='Required mount'):
        prepare_run('image', tmp_path, [], ['bash'],
            Config(state_dir=tmp_path / 'state', mcp_mounts=[{'source':'absent', 'target':'/mcp'}]), dry_run=True)
    assert not (tmp_path / 'state').exists()


def test_doctor_reports_missing_image_without_creating_state(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    runtime = MagicMock()
    runtime.runtime = 'podman'
    runtime.image_exists.return_value = False
    monkeypatch.setattr('agentbox.diagnostics.ContainerRuntime', lambda _: runtime)
    monkeypatch.setattr('agentbox.diagnostics.subprocess.run', MagicMock())
    result = CliRunner().invoke(main, ['doctor', str(tmp_path)])
    assert result.exit_code == 1
    assert 'not cached' in result.output
    assert not (tmp_path / '.local').exists()


def test_doctor_checks_agent_without_mounts_or_network(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    runtime = MagicMock()
    runtime.runtime = 'podman'
    runtime.image_exists.return_value = True
    monkeypatch.setattr('agentbox.diagnostics.ContainerRuntime', lambda _: runtime)
    run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr('agentbox.diagnostics.subprocess.run', run)
    result = CliRunner().invoke(main, ['doctor', str(tmp_path)])
    assert result.exit_code == 0, result.output
    cmd = run.call_args.args[0]
    assert '--network=none' in cmd and '--read-only' in cmd and '-v' not in cmd
    assert not (tmp_path / '.local').exists()


def test_malformed_yaml_does_not_echo_secret_value(tmp_path):
    (tmp_path / '.agentbox.yaml').write_text('toolsets: [secret-yaml-sentinel\n')
    result = CliRunner().invoke(main, ['doctor', str(tmp_path)])
    assert result.exit_code == 1
    assert 'secret-yaml-sentinel' not in result.output
