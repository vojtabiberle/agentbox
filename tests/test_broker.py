import concurrent.futures
from contextlib import closing
import http.client
import json
import socket
import threading
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from agentbox.broker import Broker, BrokerPolicy, public_addresses, reserve_budget


class UnixClient(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=5)
        self.path = str(path)

    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(self.path)


@pytest.fixture
def policy(tmp_path):
    return BrokerPolicy(socket=tmp_path/'proxy.sock', control_socket=tmp_path/'control.sock',
        ledger=tmp_path/'budget.db', kill_file=tmp_path/'STOP',
        anthropic_secret='projects/test/secrets/model/versions/latest',
        model='test-model', daily_budget_cents=100, request_reservation_cents=50,
        github_repository='org/repo', github_secret='projects/test/secrets/github/versions/latest')


@pytest.fixture
def broker(policy):
    servers=[Broker(policy),Broker(policy,controller=True)]
    for server in servers:
        threading.Thread(target=server.serve_forever,daemon=True).start()
    yield policy
    for server in servers:
        server.shutdown();server.server_close()


def request(path, method, target, body=None):
    with closing(UnixClient(path)) as conn:
        try:
            conn.request(method,target,body=json.dumps(body) if body is not None else None)
        except BrokenPipeError:
            # A kill-switch rejection can arrive before the client writes its body.
            # Still require a complete HTTP response and assert its status below.
            pass
        response=conn.getresponse()
        return response.status,response.read()


@pytest.mark.parametrize('host',['*.github.com','127.0.0.1','metadata.google.internal','api.anthropic.com','api.github.com','evil.com/path'])
def test_reject_unsafe_allowlist(policy,host):
    with pytest.raises(ValidationError):
        BrokerPolicy.model_validate({**policy.model_dump(),'allowed_hosts':[host]})


def test_mixed_private_dns_rejected():
    with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,0,'',('1.1.1.1',443)),(socket.AF_INET,socket.SOCK_STREAM,0,'',('169.254.169.254',443))]):
        with pytest.raises(PermissionError): public_addresses('allowed.example')


def test_budget_is_atomic_and_persistent(policy):
    def reserve(_):
        try: reserve_budget(policy); return True
        except PermissionError: return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(reserve, range(8)))==2
    with pytest.raises(PermissionError): reserve_budget(policy)


@pytest.mark.parametrize('target',['169.254.169.254:443','api.anthropic.com:443','github.com:80','evil.example:443'])
def test_network_bypass_denied(broker,target):
    assert request(broker.socket,'CONNECT',target)[0]==403


def test_workload_cannot_use_github_credentials(broker):
    with patch('agentbox.broker.github_token') as secret:
        assert request(broker.socket,'GET','/github/repos/org/repo/pulls')[0]==403
    secret.assert_not_called()


def test_controller_repository_and_method_scope(broker):
    with patch('agentbox.broker.github_token',return_value='secret'),patch('agentbox.broker.request_json',return_value=(200,b'[]','application/json')) as upstream:
        assert request(broker.control_socket,'GET','/github/repos/org/repo/pulls?state=open&per_page=100')[0]==200
        assert request(broker.control_socket,'GET','/github/repos/other/repo/pulls')[0]==403
        assert request(broker.control_socket,'POST','/github/repos/org/repo/pulls/1/merge',{})[0]==403
    assert upstream.call_count==1


def test_model_reservation_precedes_request_and_no_secret_in_response(broker):
    calls=[]
    def upstream(host,path,headers,body=None,method='POST'):
        calls.append(path)
        assert headers['x-api-key']=='secret-sentinel'
        if path.endswith('count_tokens'): return 200,b'{"input_tokens":10}','application/json'
        return 200,b'{"content":[]}','application/json'
    payload={'model':'test-model','max_tokens':10,'messages':[{'role':'user','content':'hi'}]}
    with patch('agentbox.broker.read_secret',return_value='secret-sentinel'),patch('agentbox.broker.request_json',side_effect=upstream):
        for expected in [200,200,403]:
            status,body=request(broker.socket,'POST','/v1/messages',payload)
            assert status==expected
            assert b'secret-sentinel' not in body
    assert calls.count('/v1/messages')==2


@pytest.mark.parametrize('mutation',[{'model':'bypass'},{'max_tokens':999999},{'tools':[{'type':'web_search_20250305'}]},{'service_tier':'priority'}])
def test_model_scope(broker,mutation):
    payload={'model':'test-model','max_tokens':10,'messages':[],**mutation}
    with patch('agentbox.broker.read_secret',return_value='secret'),patch('agentbox.broker.request_json',return_value=(200,b'{"input_tokens":1}','application/json')) as upstream:
        assert request(broker.socket,'POST','/v1/messages',payload)[0]==403
        assert all(c.args[1]!='/v1/messages' for c in upstream.call_args_list)


def test_kill_switch_denies_both_sockets(broker):
    broker.kill_file.touch()
    assert request(broker.socket,'POST','/v1/messages',{})[0]==403
    assert request(broker.control_socket,'GET','/github/repos/org/repo/pulls')[0]==403


def test_github_app_mints_scoped_short_lived_token_without_key_file(policy):
    import base64
    import subprocess
    from agentbox.broker import github_token
    private=subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048'],capture_output=True,check=True).stdout.decode()
    app=policy.model_copy(update={'github_app_id':123,'github_installation_id':456})
    with patch('agentbox.broker.read_secret',return_value=private),patch('agentbox.broker.request_json',return_value=(201,b'{"token":"short-lived"}','application/json')) as upstream:
        assert github_token(app)=='short-lived'
    args=upstream.call_args.args
    assert args[1]=='/app/installations/456/access_tokens'
    assert args[3]=={'repositories':['repo'],'permissions':{'contents':'read','pull_requests':'write'}}
    jwt=args[2]['Authorization'].split()[1]
    payload=json.loads(base64.urlsafe_b64decode(jwt.split('.')[1]+'=='))
    assert payload['iss']=='123' and payload['exp']-payload['iat']==330
    assert private not in jwt


@pytest.mark.parametrize('abstract', [False, True])
def test_systemd_ready_means_both_sockets_serve_requests(policy, tmp_path, abstract):
    import os
    import stat
    import subprocess
    import sys
    import uuid

    address = '@agentbox-test-' + uuid.uuid4().hex if abstract else str(tmp_path / 'notify')
    bound_address = '\0' + address[1:] if abstract else address
    code = (
        'import sys; from pathlib import Path; import agentbox.broker as b; '
        'b.trusted_file=lambda path: sys.argv[1]; '
        'b.broker_main.callback(Path("/unused"))'
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as ready:
        ready.bind(bound_address)
        ready.settimeout(10)
        process = subprocess.Popen(
            [sys.executable, '-c', code, policy.model_dump_json()],
            env={**os.environ, 'NOTIFY_SOCKET': address, 'PYTHONPATH': os.pathsep.join(sys.path)},
            stdout=subprocess.DEVNULL,
        )
        try:
            assert ready.recv(128) == b'READY=1'
            for endpoint in (policy.socket, policy.control_socket):
                assert stat.S_IMODE(endpoint.stat().st_mode) == 0o660
                assert request(endpoint, 'GET', '/github/repos/other/repo/pulls')[0] == 403
        finally:
            process.terminate()
            process.communicate(timeout=10)
