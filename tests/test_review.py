from unittest.mock import patch

from agentbox.review import ReviewPolicy, review_once
from agentbox.server import BatchResult, ServerPolicy


def test_reference_review_deduplicates_and_never_executes_repository(tmp_path):
    config=ReviewPolicy(repository='org/repo',reviewer='person',ledger=tmp_path/'reviews.db')
    policy=ServerPolicy(image='example.org/agent@sha256:'+'a'*64, workspace_root=tmp_path,
        command=['claude','-p'],kill_file=tmp_path/'STOP')
    sha='a'*40
    posts=[]
    def github(config,path,body=None,diff=False):
        if path.startswith('/pulls?'):
            return [{'number':1,'head':{'sha':sha},'requested_reviewers':[{'login':'person'}]}]
        if diff: return b'+ malicious .agentbox.yaml and Dockerfile content'
        if body is not None: posts.append(body);return {}
        return {'head':{'sha':sha}}
    with patch('agentbox.review.load_policy',return_value=policy),patch('agentbox.review.github',side_effect=github),patch('agentbox.review.execute',return_value=BatchResult('id',0,'exit',b'No findings.')) as execute:
        assert review_once(config)==1
        assert review_once(config)==0
        assert execute.call_count==1
        assert not execute.call_args.args[1].exists()  # Empty temporary workspace removed.
        assert b'malicious' in execute.call_args.args[2]
    assert len(posts)==1 and sha in posts[0]['body']


def test_changed_head_is_not_published(tmp_path):
    config=ReviewPolicy(repository='org/repo',reviewer='person',ledger=tmp_path/'reviews.db')
    policy=ServerPolicy(image='example.org/agent@sha256:'+'a'*64,workspace_root=tmp_path,command=['true'])
    replies=[[{'number':1,'head':{'sha':'a'*40},'requested_reviewers':[{'login':'person'}]}],b'diff',{'head':{'sha':'b'*40}}]
    with patch('agentbox.review.load_policy',return_value=policy),patch('agentbox.review.github',side_effect=replies) as github,patch('agentbox.review.execute',return_value=BatchResult('id',0,'exit',b'Review')):
        assert review_once(config)==0
        assert github.call_count==3
