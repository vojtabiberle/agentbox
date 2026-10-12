import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from agentbox.cli import main
from agentbox.config import Config
from agentbox.exceptions import ConfigError
from agentbox.execution import prepare_run
from agentbox.state import state_home


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git(
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
        cwd=repo,
    )
    worktree = tmp_path / "wt" / "task"
    _git("worktree", "add", "-q", str(worktree), "-b", "task", cwd=repo)
    return repo, worktree


def test_default_scope_is_workspace() -> None:
    assert Config().state_scope == "workspace"


def test_workspace_scope_separates_worktrees(
    tmp_path: Path, repo_with_worktree: tuple[Path, Path]
) -> None:
    repo, worktree = repo_with_worktree
    assert state_home(tmp_path / "s", repo, "claude") != state_home(
        tmp_path / "s", worktree, "claude"
    )


def test_repository_scope_shares_home_across_worktrees(
    tmp_path: Path, repo_with_worktree: tuple[Path, Path]
) -> None:
    repo, worktree = repo_with_worktree
    root = tmp_path / "s"
    assert state_home(root, repo, "claude", "repository") == state_home(
        root, worktree, "claude", "repository"
    )


def test_repository_scope_separates_repositories(tmp_path: Path) -> None:
    homes = set()
    for name in ("a", "b"):
        repo = tmp_path / name
        repo.mkdir()
        _git("init", "-q", cwd=repo)
        homes.add(state_home(tmp_path / "s", repo, "claude", "repository"))
    assert len(homes) == 2


def test_repository_scope_outside_git_is_error(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ConfigError, match="requires a Git repository"):
        state_home(tmp_path / "s", plain, "claude", "repository")


def test_repository_scope_flows_through_prepare_run(
    tmp_path: Path, repo_with_worktree: tuple[Path, Path]
) -> None:
    repo, worktree = repo_with_worktree
    config = Config(state_dir=tmp_path / "s", state_scope="repository")
    specs = [prepare_run("image", path, [], ["bash"], config) for path in (repo, worktree)]
    assert specs[0].home is not None and specs[0].home == specs[1].home


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def test_state_show_prints_repository_scope(
    tmp_path: Path, repo_with_worktree: tuple[Path, Path], isolated_home: Path
) -> None:
    _, worktree = repo_with_worktree
    (worktree / ".agentbox.yaml").write_text(
        yaml.safe_dump({"state_scope": "repository", "state_dir": str(tmp_path / "s")})
    )
    result = CliRunner().invoke(main, ["state", "show", str(worktree)])
    assert result.exit_code == 0, result.output
    assert "Scope: repository" in result.output


def test_state_reset_help_mentions_shared_repository_home(isolated_home: Path) -> None:
    result = CliRunner().invoke(main, ["state", "reset", "--help"])
    text = " ".join(result.output.split())
    assert "state_scope: repository" in text
    assert "shared by all worktrees" in text
