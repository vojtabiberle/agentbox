import os
import subprocess

import pytest

from agentbox.plugins import PluginManager


def test_infrastructure_dependencies_and_pins():
    manager = PluginManager()
    plugins = manager.load(["terraform", "kubernetes-extras"])
    assert [p.manifest.name for p in plugins] == ["base", "kubernetes", "terraform", "kubernetes-extras"]
    for name in ["terraform", "kubernetes-extras"]:
        script = manager.get_plugin(name).manifest.dockerfile
        assert "sha256sum -c" in script
        assert "x86_64)" in script and "aarch64)" in script


@pytest.mark.skipif(not os.environ.get("AGENTBOX_INFRA_TEST_IMAGE"), reason="Set AGENTBOX_INFRA_TEST_IMAGE")
@pytest.mark.parametrize("command", [["terraform", "version"], ["kubectx", "--version"],
                                     ["kubens", "--version"], ["stern", "--version"]])
def test_infrastructure_commands_start(command):
    result = subprocess.run([os.environ.get("AGENTBOX_TEST_RUNTIME", "podman"), "run", "--rm",
        "--network=none", os.environ["AGENTBOX_INFRA_TEST_IMAGE"], *command],
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
