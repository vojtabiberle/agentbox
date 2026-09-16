from click.testing import CliRunner

from agentbox.cli import main
from agentbox.plugins import PluginManager
from agentbox.plugins.models import ToolsetManifest


def test_inventory_is_optional_for_existing_manifests():
    assert ToolsetManifest(name="old").provides == []


def test_builtin_inventories_and_inspection():
    plugins = PluginManager().list_available()
    assert all(plugin.manifest.provides for plugin in plugins)
    result = CliRunner().invoke(main, ["toolset", "kubernetes"])
    assert result.exit_code == 0
    assert all(name in result.output for name in ["Provides:", "kubectl", "helm", "kustomize"])
    result = CliRunner().invoke(main, ["toolset", "cloud-aws"])
    assert result.exit_code == 0
    assert "required=false relabel=true" in result.output
    assert "AWS_CONFIG_FILE" in result.output
