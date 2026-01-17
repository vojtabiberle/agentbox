# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

agentbox is a Python CLI that runs AI coding agents (Claude Code, etc.) inside isolated Podman/Docker containers. The container has access only to a specified workspace directory, keeping the rest of the system isolated.

## Development Commands

```bash
# Install in development mode
pip install -e .

# Run locally
agentbox run ~/workspace
agentbox run ~/workspace --bash
agentbox build --rebuild

# Run tests (when added)
pytest
```

## Architecture

```
src/agentbox/
├── cli.py          # Click CLI entrypoint (run, build, config commands)
├── config.py       # Pydantic config model, YAML loading from ~/.config/agentbox/
├── container.py    # Podman/Docker runtime abstraction
├── image.py        # Dockerfile building via Jinja2 templates
├── agents/         # Agent implementations
│   ├── base.py     # Agent ABC
│   └── claude.py   # Claude Code agent
└── templates/
    └── Dockerfile.j2   # Jinja2 template with toolset conditionals
```

### Key patterns

- **Config discovery**: Checks `.agentbox.yaml` in cwd, then `~/.config/agentbox/config.yaml`
- **Toolsets**: Dockerfile is generated from `templates/Dockerfile.j2` with conditional sections per toolset
- **Container runtime**: Abstracts Podman/Docker differences in `container.py`
- **Credential mounting**: Read-only mounts for cloud CLI credentials based on config

### Adding a new toolset

1. Add conditional block in `src/agentbox/templates/Dockerfile.j2`
2. Document in README.md configuration section

### Adding a new agent

1. Create `src/agentbox/agents/newagent.py` implementing `Agent` ABC
2. Register in `src/agentbox/agents/__init__.py` `_AGENTS` dict
