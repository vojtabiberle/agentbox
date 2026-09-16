# agentbox contributor guide

agentbox runs Claude Code and Hermes CLI in Podman/Docker containers. The selected
workspace, private persistent HOME and explicitly configured mounts are accessible;
the host HOME is not mounted wholesale. Networking remains enabled.

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check src/agentbox
ruff format --check src/agentbox
mypy src/agentbox
agentbox run ~/workspace --bash
agentbox build --agent hermes
```

Opt-in real-container tests are documented in README. Never substitute passing
Dockerfile string assertions for a successful build and CLI smoke test. Keep model
calls separate from default CI; they require user-configured authentication.

## Architecture

- `cli.py`: Click commands, agent selection, workspace and argument handling.
- `config.py`: Pydantic models; cwd config takes precedence over global config.
- `container.py`: runtime commands, mounts, UID mapping and private HOME creation.
- `git.py`: detects worktrees and required Git directory mounts.
- `image.py`: resolves toolsets, renders Dockerfiles and computes image tags.
- `agents/`: Agent interface and Claude/Hermes integrations.
- `plugins/`: YAML manifests, discovery and dependency resolution.
- `templates/Dockerfile.j2`: shared image skeleton with plugin fragments.

## Extensions

Add a toolset under `src/agentbox/plugins/builtin/<name>/toolset.yaml`; use
`depends_on` for prerequisites. Test discovery, image integration and executable
startup; document the toolset in README. Do not hard-code toolsets in the template.

Add an agent implementation under `agents/` and register it in `_AGENTS`.
Declare required toolsets and explicit host mounts through the Agent interface.
Agent-specific installation and host configuration do not belong in the base
image or generic runtime. Preserve private HOME isolation across projects and
agents. Never mount host credentials implicitly when adding an integration.

## Changes and releases

Preserve unrelated local work. Keep personal tool configuration, execution logs
and secrets out of commits. Update README and ROADMAP with behavior changes.
Keep `pyproject.toml` and `src/agentbox/__init__.py` versions synchronized.
Verify built wheel and source distribution with a clean installation before release.
