"""Git worktree detection for transparent git directory mounting."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitWorktreeInfo:
    """Information about a git worktree's directory layout."""

    git_common_dir: Path
    git_dir: Path
    needs_mount: bool


def detect_worktree(workspace: Path) -> GitWorktreeInfo | None:
    """Detect if workspace is a git worktree and return mount info.

    Returns None for non-git directories or on any error.
    Returns GitWorktreeInfo with needs_mount=False for regular repos
    where .git is already inside the workspace.
    """
    try:
        return _detect_via_git_command(workspace)
    except (FileNotFoundError, subprocess.SubprocessError):
        # git not installed or command failed — try file parsing fallback
        pass

    try:
        return _detect_via_file_parsing(workspace)
    except (OSError, ValueError):
        pass

    return None


def _detect_via_git_command(workspace: Path) -> GitWorktreeInfo | None:
    """Detect worktree using git rev-parse."""
    result = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "--git-common-dir", "--git-dir"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return None

    lines = result.stdout.strip().splitlines()
    if len(lines) != 2:
        return None

    raw_common_dir, raw_git_dir = lines

    # Resolve relative paths against workspace
    git_common_dir = (workspace / raw_common_dir).resolve()
    git_dir = (workspace / raw_git_dir).resolve()

    needs_mount = not _is_under(git_common_dir, workspace)
    return GitWorktreeInfo(
        git_common_dir=git_common_dir,
        git_dir=git_dir,
        needs_mount=needs_mount,
    )


def _detect_via_file_parsing(workspace: Path) -> GitWorktreeInfo | None:
    """Detect worktree by parsing .git file and commondir file."""
    dot_git = workspace / ".git"

    if not dot_git.exists():
        return None

    # Regular repo — .git is a directory
    if dot_git.is_dir():
        return GitWorktreeInfo(
            git_common_dir=dot_git.resolve(),
            git_dir=dot_git.resolve(),
            needs_mount=False,
        )

    # Worktree or submodule — .git is a file with "gitdir: <path>"
    content = dot_git.read_text().strip()
    if not content.startswith("gitdir:"):
        return None

    gitdir_path = content[len("gitdir:") :].strip()
    git_dir = (workspace / gitdir_path).resolve()

    # Read commondir file if it exists (points to main repo's .git)
    commondir_file = git_dir / "commondir"
    if commondir_file.exists():
        commondir_rel = commondir_file.read_text().strip()
        git_common_dir = (git_dir / commondir_rel).resolve()
    else:
        git_common_dir = git_dir

    needs_mount = not _is_under(git_common_dir, workspace)
    return GitWorktreeInfo(
        git_common_dir=git_common_dir,
        git_dir=git_dir,
        needs_mount=needs_mount,
    )


def _is_under(path: Path, parent: Path) -> bool:
    """Check if path is under parent directory."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
