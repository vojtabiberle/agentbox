"""Tests for git worktree detection."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from agentbox.git import detect_worktree


class TestDetectWorktreeNonGit:
    """Tests for non-git directories."""

    def test_non_git_directory_returns_none(self, tmp_path: Path) -> None:
        """Non-git directory returns None."""
        result = detect_worktree(tmp_path)
        assert result is None


class TestDetectWorktreeRegularRepo:
    """Tests for regular git repositories."""

    def test_regular_repo_needs_no_mount(self, tmp_path: Path) -> None:
        """Regular repo (.git is a directory) returns needs_mount=False."""
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)

        result = detect_worktree(tmp_path)
        assert result is not None
        assert result.needs_mount is False
        assert result.git_common_dir == (tmp_path / ".git").resolve()
        assert result.git_dir == (tmp_path / ".git").resolve()


class TestDetectWorktreeActualWorktree:
    """Tests using real git worktrees."""

    @staticmethod
    def _init_repo_with_commit(repo_path: Path) -> None:
        """Initialize a git repo with one commit (CI-safe)."""
        git = ["git", "-C", str(repo_path)]
        subprocess.run([*git, "init"], capture_output=True, check=True)
        subprocess.run(
            [*git, "config", "user.email", "test@test.com"],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            [*git, "config", "user.name", "Test"],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            [*git, "commit", "--allow-empty", "-m", "init"],
            capture_output=True,
            check=True,
        )

    def test_worktree_needs_mount(self, tmp_path: Path) -> None:
        """Worktree (.git is a file) returns needs_mount=True with correct paths."""
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        self._init_repo_with_commit(main_repo)

        wt_path = tmp_path / "worktree"
        subprocess.run(
            ["git", "-C", str(main_repo), "worktree", "add", str(wt_path)],
            capture_output=True,
            check=True,
        )

        result = detect_worktree(wt_path)
        assert result is not None
        assert result.needs_mount is True
        assert result.git_common_dir == (main_repo / ".git").resolve()

    def test_worktree_git_dir_under_common_dir(self, tmp_path: Path) -> None:
        """Worktree's git_dir is under main .git/worktrees/."""
        main_repo = tmp_path / "main"
        main_repo.mkdir()
        self._init_repo_with_commit(main_repo)

        wt_path = tmp_path / "worktree"
        subprocess.run(
            ["git", "-C", str(main_repo), "worktree", "add", str(wt_path)],
            capture_output=True,
            check=True,
        )

        result = detect_worktree(wt_path)
        assert result is not None
        # git_dir should be under git_common_dir/worktrees/
        assert str(result.git_dir).startswith(str(result.git_common_dir))


class TestDetectWorktreeFallback:
    """Tests for file-parsing fallback when git command is unavailable."""

    def test_fallback_regular_repo(self, tmp_path: Path) -> None:
        """File parsing detects regular repo when git unavailable."""
        dot_git = tmp_path / ".git"
        dot_git.mkdir()

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(tmp_path)

        assert result is not None
        assert result.needs_mount is False

    def test_fallback_worktree(self, tmp_path: Path) -> None:
        """File parsing detects worktree when git unavailable."""
        # Simulate a worktree structure
        main_git = tmp_path / "main" / ".git"
        main_git.mkdir(parents=True)

        # Create the worktrees dir structure that a real git worktree would have
        wt_git_dir = main_git / "worktrees" / "wt"
        wt_git_dir.mkdir(parents=True)
        (wt_git_dir / "commondir").write_text("../..")

        # Create the worktree workspace with .git file
        wt_workspace = tmp_path / "wt"
        wt_workspace.mkdir()
        (wt_workspace / ".git").write_text(f"gitdir: {wt_git_dir}")

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(wt_workspace)

        assert result is not None
        assert result.needs_mount is True
        assert result.git_common_dir == main_git.resolve()
        assert result.git_dir == wt_git_dir.resolve()

    def test_fallback_no_git_file(self, tmp_path: Path) -> None:
        """Returns None when no .git file/dir exists and git unavailable."""
        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(tmp_path)

        assert result is None


class TestDetectWorktreeFallbackEdgeCases:
    """Tests for edge cases in file-parsing fallback."""

    def test_empty_git_file(self, tmp_path: Path) -> None:
        """Empty .git file returns None."""
        (tmp_path / ".git").write_text("")

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(tmp_path)

        assert result is None

    def test_git_file_without_gitdir_prefix(self, tmp_path: Path) -> None:
        """A .git file without 'gitdir:' prefix returns None."""
        (tmp_path / ".git").write_text("something unexpected")

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(tmp_path)

        assert result is None

    def test_git_file_gitdir_with_whitespace(self, tmp_path: Path) -> None:
        """gitdir: line with extra whitespace is handled."""
        main_git = tmp_path / "main" / ".git"
        main_git.mkdir(parents=True)

        wt_git_dir = main_git / "worktrees" / "wt"
        wt_git_dir.mkdir(parents=True)
        (wt_git_dir / "commondir").write_text("  ../..  \n")

        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / ".git").write_text(f"gitdir:   {wt_git_dir}  \n")

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(wt)

        assert result is not None
        assert result.needs_mount is True
        assert result.git_common_dir == main_git.resolve()

    def test_git_file_no_commondir_file(self, tmp_path: Path) -> None:
        """When commondir file is missing, git_dir is used as common_dir."""
        some_git_dir = tmp_path / "elsewhere" / "git-stuff"
        some_git_dir.mkdir(parents=True)

        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / ".git").write_text(f"gitdir: {some_git_dir}")

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(wt)

        assert result is not None
        assert result.git_common_dir == some_git_dir.resolve()
        assert result.git_dir == some_git_dir.resolve()

    def test_git_dir_is_symlink_to_directory(self, tmp_path: Path) -> None:
        """A .git symlink pointing to a directory is treated as a directory."""
        real_git = tmp_path / "real_git"
        real_git.mkdir()

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").symlink_to(real_git)

        with patch("agentbox.git._detect_via_git_command", side_effect=FileNotFoundError):
            result = detect_worktree(workspace)

        assert result is not None
        # Symlink to directory → treated as regular repo
        assert result.needs_mount is False


class TestDetectWorktreeErrors:
    """Tests for error handling."""

    def test_subprocess_timeout_returns_none(self, tmp_path: Path) -> None:
        """Subprocess timeout returns None."""
        with patch(
            "agentbox.git.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5),
        ):
            result = detect_worktree(tmp_path)

        assert result is None

    def test_subprocess_error_returns_none(self, tmp_path: Path) -> None:
        """Subprocess error returns None."""
        with patch(
            "agentbox.git.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            result = detect_worktree(tmp_path)

        assert result is None

    def test_permission_error_returns_none(self, tmp_path: Path) -> None:
        """Permission error during file parsing returns None."""
        with patch(
            "agentbox.git.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            # Also make file parsing fail
            with patch("agentbox.git._detect_via_file_parsing", side_effect=OSError):
                result = detect_worktree(tmp_path)

        assert result is None
