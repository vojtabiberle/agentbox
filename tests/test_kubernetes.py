"""Minimal Kubernetes toolset and opt-in offline installation checks."""

import os
import subprocess
from unittest.mock import MagicMock

import pytest

from agentbox.config import Config
from agentbox.image import ImageBuilder


def test_kubernetes_discovery_dependencies_and_image():
    builder = ImageBuilder(MagicMock(), Config(toolsets=["kubernetes"]))
    plugins = builder.plugin_manager.load(builder.config.toolsets)
    assert [plugin.manifest.name for plugin in plugins] == ["base", "kubernetes"]
    assert plugins[-1].origin == "builtin"
    dockerfile = builder._render_dockerfile()
    assert "dnf install -y kubectl helm kustomize" in dockerfile
    # Cluster credentials require explicit user configuration.
    assert builder.plugin_manager.get_all_mounts() == []


@pytest.mark.skipif(
    not os.environ.get("AGENTBOX_KUBERNETES_TEST_IMAGE"),
    reason="Set AGENTBOX_KUBERNETES_TEST_IMAGE to an image containing the toolset",
)
@pytest.mark.parametrize(
    "command",
    [
        ["kubectl", "version", "--client=true"],
        ["helm", "version", "--short"],
        ["kustomize", "version"],
    ],
)
def test_kubernetes_tools_run_without_cluster(command):
    result = subprocess.run(
        [
            "podman",
            "run",
            "--rm",
            "--network=none",
            "--userns=keep-id",
            "--security-opt=no-new-privileges",
            os.environ["AGENTBOX_KUBERNETES_TEST_IMAGE"],
            *command,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip()
