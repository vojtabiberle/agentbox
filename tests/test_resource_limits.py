import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from agentbox.cli import main
from agentbox.config import Config
from agentbox.container import ContainerRuntime
from agentbox.execution import prepare_run


@pytest.mark.parametrize('limits', [{'memory':'-1g'}, {'memory':'1g --privileged'}, {'memory':'0'}, {'cpus':0}, {'cpus':float('inf')}, {'cpus':float('nan')}, {'pids_limit':-1}, {'pids_limit':True}, {'network':'host'}])
def test_invalid_limits_rejected(limits):
    with pytest.raises(ValidationError):
        Config(limits=limits)


@pytest.mark.parametrize('engine', ['podman','docker'])
def test_limits_render_for_both_engines(tmp_path, monkeypatch, engine):
    monkeypatch.setattr(ContainerRuntime, '_verify_runtime', lambda _: None)
    monkeypatch.setattr(ContainerRuntime, 'is_rootless_docker', lambda _: False)
    spec=prepare_run('image', tmp_path, [], ['bash'], Config(state_dir=tmp_path/'state', limits={'memory':'256m','cpus':0.5,'pids_limit':32,'network':'none'}), dry_run=True)
    cmd=ContainerRuntime(engine).build_command(spec)
    assert cmd[cmd.index('--memory')+1]=='256m'
    assert cmd[cmd.index('--cpus')+1]=='0.5'
    assert cmd[cmd.index('--pids-limit')+1]=='32'
    assert '--network=none' in cmd


def test_cli_limits_override_config_without_losing_other_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr('agentbox.cli.ContainerRuntime', MagicMock())
    (tmp_path/'.agentbox.yaml').write_text('limits:\n  memory: 512m\n  cpus: 2\n')
    result=CliRunner().invoke(main,['run',str(tmp_path),'--dry-run','--cpus','1.5','--network','none'])
    assert result.exit_code==0, result.output
    assert json.loads(result.output)['limits']=={'memory':'512m','cpus':1.5,'pids_limit':None,'network':'none'}


def test_real_resource_limits_and_offline_network(tmp_path):
    engine=os.environ.get('AGENTBOX_TEST_RUNTIME')
    image=os.environ.get('AGENTBOX_TEST_IMAGE')
    if engine not in ('podman','docker') or not image:
        pytest.skip('Set AGENTBOX_TEST_RUNTIME/IMAGE')
    runtime=ContainerRuntime(engine)
    spec=prepare_run(image,tmp_path,[],['sleep','60'],Config(state_dir=tmp_path/'state',limits={'memory':'128m','cpus':0.5,'pids_limit':32,'network':'none'}),interactive=False)
    cmd=runtime.build_command(spec)
    cmd.insert(2,'--detach')
    started=subprocess.run(cmd,check=True,capture_output=True,text=True)
    identity=started.stdout.strip()
    try:
        info=json.loads(subprocess.run([engine,'inspect',identity],check=True,capture_output=True,text=True).stdout)[0]
        host=info['HostConfig']
        assert host['Memory']==128*1024*1024
        assert host['PidsLimit']==32
        assert host.get('NanoCpus')==500000000 or host['CpuQuota']/host['CpuPeriod']==0.5
        result=subprocess.run([engine,'exec',identity,'bash','-ec','test "$(cat /sys/fs/cgroup/memory.max)" = 134217728; test "$(cat /sys/fs/cgroup/pids.max)" = 32; test "$(ls /sys/class/net)" = lo'],capture_output=True,text=True)
        assert result.returncode==0, result.stderr
    finally:
        subprocess.run([engine,'rm','-f',identity],check=True,capture_output=True)
