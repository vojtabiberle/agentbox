# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

agentbox provides `claude-danger`, a bash script that runs Claude Code inside an isolated Podman container. The container has access only to a specified workspace directory, keeping the rest of the system isolated.

## Usage

```bash
bin/claude-danger <workspace-directory>
```

The script:
1. Creates the workspace directory if it doesn't exist
2. Builds a Fedora 41-based container image on first run (includes Node.js, Python, Go, Rust, PHP, and cloud CLIs)
3. Creates a persistent volume for Claude credentials
4. Runs Claude Code with `--dangerously-skip-permissions` inside the container

## Architecture

- **bin/claude-danger**: Main entry point. Self-contained bash script that embeds the Dockerfile as a heredoc and handles container lifecycle via Podman.
- **claude-danger-config volume**: Persistent Podman volume storing Claude credentials across runs.
- Container runs rootless with `--userns=keep-id` and `--security-opt=no-new-privileges`.
