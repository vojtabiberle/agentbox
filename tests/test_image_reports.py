import json
import runpy
from pathlib import Path

import pytest

verify = runpy.run_path(str(Path(__file__).parents[1] / 'scripts/verify-image-reports.py'))['verify']


def reports(tmp_path):
    (tmp_path/'rpm-packages.txt').write_text('bash\t5.3-1.fc44\n')
    (tmp_path/'sbom.syft.json').write_text(json.dumps({'distro':{'versionID':'44'},'artifacts':[{'name':'bash','version':'0:5.3-1.fc44','type':'rpm'}]}))
    (tmp_path/'sbom.cdx.json').write_text(json.dumps({'components':[{'name':'bash','version':'5.3-1.fc44','purl':'pkg:rpm/fedora/bash@5.3-1.fc44'}]}))
    (tmp_path/'vulnerabilities.json').write_text(json.dumps({'distro':{'name':'fedora','version':'44'},'descriptor':{'db':{'status':{'valid':True},'providers':{'fedora':{}}}},'matches':[{'vulnerability':{'severity':'High'}}]}))


def test_inventory_matches_installed_versions_and_keeps_findings(tmp_path):
    reports(tmp_path)
    assert 'High' in verify(tmp_path)


@pytest.mark.parametrize('file,key', [('sbom.syft.json','artifacts'),('sbom.cdx.json','components')])
def test_empty_inventory_is_rejected_even_when_scan_is_green(tmp_path,file,key):
    reports(tmp_path)
    (tmp_path/file).write_text(json.dumps({key:[]}))
    with pytest.raises(ValueError,match='omits installed'):
        verify(tmp_path)


def test_wrong_package_version_is_rejected(tmp_path):
    reports(tmp_path)
    (tmp_path/'rpm-packages.txt').write_text('bash\t5.3-2.fc44\n')
    with pytest.raises(ValueError,match='omits installed'):
        verify(tmp_path)


def test_missing_os_scan_is_rejected(tmp_path):
    reports(tmp_path)
    (tmp_path/'vulnerabilities.json').write_text('{"matches":[]}')
    with pytest.raises(ValueError,match='does not identify Fedora'):
        verify(tmp_path)


@pytest.mark.parametrize('mutation', ['wrong-version','missing-feed'])
def test_incorrect_os_coverage_is_rejected(tmp_path, mutation):
    reports(tmp_path)
    path=tmp_path/'vulnerabilities.json'
    data=json.loads(path.read_text())
    if mutation=='wrong-version':
        data['distro']['version']='43'
    else:
        data['descriptor']['db']['providers']={}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='does not identify Fedora'):
        verify(tmp_path)
