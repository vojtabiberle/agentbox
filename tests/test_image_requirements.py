import os
import subprocess
from unittest.mock import MagicMock

import pytest

from agentbox.container import ContainerRuntime
from agentbox.exceptions import ConfigError
from agentbox.plugins import PluginManager


def runtime(monkeypatch):
    monkeypatch.setattr(ContainerRuntime, '_verify_runtime', lambda _: None)
    return ContainerRuntime('podman')


def test_probe_has_no_mounts_credentials_or_network(monkeypatch):
    engine=runtime(monkeypatch)
    run=MagicMock(return_value=subprocess.CompletedProcess([],0,''))
    monkeypatch.setattr('agentbox.container.subprocess.run',run)
    engine.check_executables('image',['claude','git'])
    cmd=run.call_args.args[0]
    assert '--network=none' in cmd and '--read-only' in cmd and '--cap-drop=ALL' in cmd
    assert '-v' not in cmd and '-e' not in cmd
    assert cmd[-2:]==['claude','git']
    assert run.call_args.kwargs['timeout']==30


def test_missing_tool_does_not_echo_arbitrary_image_output(monkeypatch):
    engine=runtime(monkeypatch)
    monkeypatch.setattr('agentbox.container.subprocess.run',MagicMock(return_value=subprocess.CompletedProcess([],1,'secret-sentinel\ncodex\n')))
    with pytest.raises(ConfigError,match='codex') as error:
        engine.check_executables('image',['codex'])
    assert 'secret-sentinel' not in str(error.value)


def test_invalid_command_rejected_without_running(monkeypatch):
    engine=runtime(monkeypatch)
    run=MagicMock()
    monkeypatch.setattr('agentbox.container.subprocess.run',run)
    with pytest.raises(ConfigError):
        engine.check_executables('image',['$(touch /tmp/pwned)'])
    run.assert_not_called()


def test_descriptive_resources_not_treated_as_commands():
    manager=PluginManager()
    manager.load(['ghostty','claude'])
    assert 'claude' in manager.get_executables()
    assert 'xterm-ghostty terminfo' not in manager.get_executables()


def test_real_image_accepts_installed_and_rejects_missing_tools():
    engine=os.environ.get('AGENTBOX_TEST_RUNTIME')
    image=os.environ.get('AGENTBOX_TEST_IMAGE')
    if engine not in ('podman','docker') or not image:
        pytest.skip('Set AGENTBOX_TEST_RUNTIME/IMAGE')
    rt=ContainerRuntime(engine)
    rt.check_executables(image,['git','hermes'])
    with pytest.raises(ConfigError,match='agentbox-nonexistent-executable'):
        rt.check_executables(image,['agentbox-nonexistent-executable'])


def test_incompatible_prebuilt_fails_before_state_creation(tmp_path, monkeypatch):
    from pathlib import Path
    from click.testing import CliRunner
    from agentbox.cli import main
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'host')
    engine=MagicMock()
    engine.check_executables.side_effect=ConfigError('Image does not satisfy required executables: claude')
    monkeypatch.setattr('agentbox.cli.ContainerRuntime', lambda _: engine)
    result=CliRunner().invoke(main,['run',str(tmp_path),'--image','example:base'])
    assert result.exit_code==1
    assert not (tmp_path / 'host').exists()
    engine.run.assert_not_called()


def test_timed_out_probe_is_removed(monkeypatch):
    engine=runtime(monkeypatch)
    run=MagicMock(side_effect=[subprocess.TimeoutExpired('probe',30),subprocess.CompletedProcess([],0,'')])
    monkeypatch.setattr('agentbox.container.subprocess.run',run)
    with pytest.raises(ConfigError,match='container removed'):
        engine.check_executables('image',['claude'])
    first=run.call_args_list[0].args[0]
    name=first[first.index('--name')+1]
    assert run.call_args_list[1].args[0]==['podman','rm','-f',name]


def test_failed_probe_cleanup_is_reported_with_owned_container_name(monkeypatch):
    engine=runtime(monkeypatch)
    run=MagicMock(side_effect=[subprocess.TimeoutExpired('probe',30),subprocess.CalledProcessError(1,'rm')])
    monkeypatch.setattr('agentbox.container.subprocess.run',run)
    with pytest.raises(ConfigError,match='remove container agentbox-probe-.* manually'):
        engine.check_executables('image',['claude'])
