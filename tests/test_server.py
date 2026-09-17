import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from agentbox.cli import main
from agentbox.exceptions import ConfigError
from agentbox.server import ServerPolicy, execute, server_command, trusted_file


@pytest.fixture
def policy(tmp_path):
    return ServerPolicy(image='example.org/agent@sha256:' + 'a'*64,
                        workspace_root=tmp_path, command=['sh', '-c', 'cat'],
                        kill_file=tmp_path/'STOP')


def test_policy_cannot_expand_surface(policy, tmp_path):
    for extra in ({'mounts': ['/etc']}, {'runtime':'docker'}, {'network':'host'},
                  {'credentials':{'github':True}}, {'image':'latest'}, {'timeout_seconds':0}):
        with pytest.raises(ValidationError):
            ServerPolicy.model_validate({**policy.model_dump(), **extra})


def test_server_ignores_poisoned_project_configuration(policy, tmp_path, monkeypatch):
    (tmp_path/'.agentbox.yaml').write_text('not: [valid')
    monkeypatch.chdir(tmp_path)
    with patch('agentbox.server.load_policy', return_value=policy), patch('agentbox.server.execute') as run:
        from agentbox.server import BatchResult
        run.return_value = BatchResult('id', 0, 'exit', b'private-output')
        result = CliRunner().invoke(main, ['server','run',str(tmp_path)], input='prompt')
    assert result.exit_code == 0, result.output
    assert 'private-output' not in result.output


def test_server_command_boundary(policy, tmp_path):
    with patch('os.getuid', return_value=1000), patch('os.getgid',return_value=1000):
        cmd = server_command(policy, tmp_path, 'owned')
    assert '--network=none' in cmd and '--cap-drop=ALL' in cmd
    assert '--read-only' in cmd and '--log-driver=none' in cmd
    assert cmd[cmd.index('--user')+1] == '1000:1000'
    assert cmd[cmd.index('--entrypoint')+1] == 'sh'
    assert cmd.count('--volume') == 1
    assert f'{tmp_path}:/workspace:ro,Z' in cmd
    assert '--pull=never' in cmd
    assert not any('SSH_AUTH_SOCK' in arg for arg in cmd)


def test_workspace_escape(policy, tmp_path):
    (tmp_path/'escape').symlink_to('/etc', target_is_directory=True)
    with pytest.raises(ConfigError,match='outside'):
        server_command(policy, tmp_path/'escape', 'owned')


def test_host_root_rejected(policy, tmp_path):
    with patch('os.getuid', return_value=0), pytest.raises(ConfigError,match='unprivileged'):
        server_command(policy,tmp_path,'owned')


def test_root_controlled_policy_required(tmp_path):
    f=tmp_path/'policy.yaml'; f.write_text('image: anything')
    with pytest.raises(ConfigError,match='root-controlled'):
        trusted_file(f)


def test_kill_switch_prevents_start(policy, tmp_path):
    policy.kill_file.touch()
    with patch('subprocess.Popen') as start, pytest.raises(ConfigError,match='kill switch'):
        execute(policy,tmp_path)
    start.assert_not_called()


@pytest.mark.skipif(not os.environ.get('AGENTBOX_SERVER_TEST_IMAGE'), reason='Set digest-pinned AGENTBOX_SERVER_TEST_IMAGE')
def test_real_server_boundary_and_cleanup(tmp_path):
    image=os.environ['AGENTBOX_SERVER_TEST_IMAGE']
    policy=ServerPolicy(image=image, workspace_root=tmp_path, command=['sh','-c',
        'test "$(id -u)" != 0 && test "$(ls /sys/class/net)" = lo && '
        '! touch /workspace/forbidden && ! touch /etc/forbidden && '
        'touch "$HOME/temporary" && cat'], kill_file=tmp_path/'STOP')
    result=execute(policy,tmp_path,b'roundtrip')
    assert result.returncode==0, result.output
    assert result.output.endswith(b'roundtrip')
    assert not (tmp_path/'forbidden').exists()
    slow=policy.model_copy(update={'command':['sleep','30'],'timeout_seconds':1})
    result=execute(slow,tmp_path)
    assert result.reason=='timeout'
    assert subprocess.run(['podman','container','exists','agentbox-server-'+result.run_id]).returncode==1
    noisy=policy.model_copy(update={'command':['sh','-c','yes output'],'output_bytes':1024})
    assert execute(noisy,tmp_path).reason=='output_limit'


@pytest.mark.skipif(not os.environ.get('AGENTBOX_SERVER_TEST_IMAGE'), reason='Set AGENTBOX_SERVER_TEST_IMAGE')
def test_real_container_bridge_has_no_direct_network(tmp_path):
    import socketserver
    import threading
    class Reply(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(65536)
            self.request.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nOK')
    socket=tmp_path/'broker.sock'
    with socketserver.UnixStreamServer(str(socket),Reply) as broker:
        threading.Thread(target=broker.serve_forever,daemon=True).start()
        try:
            policy=ServerPolicy(image=os.environ['AGENTBOX_SERVER_TEST_IMAGE'],workspace_root=tmp_path,
                broker_socket=socket, command=['python3','-c',
                'import os,urllib.request,socket; '
                'assert os.listdir("/sys/class/net")==["lo"]; '
                'print(urllib.request.urlopen(os.environ["ANTHROPIC_BASE_URL"]).read().decode())'],
                kill_file=tmp_path/'STOP')
            result=execute(policy,tmp_path)
            assert result.returncode==0, result.output
            assert result.output.strip()==b'OK'
        finally: broker.shutdown()
