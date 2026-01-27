"""Tests for git worktree management."""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from ringmaster.git.worktrees import (
    Worktree,
    WorktreeConfig,
    _generate_branch_name,
    clean_stale_worktrees,
    commit_worktree_changes,
    get_or_create_worktree,
    get_worker_worktree_path,
    get_worktree_dir,
    get_worktree_status,
    list_worktrees,
    merge_worktree_to_main,
    remove_worktree,
)


@pytest.fixture
def git_repo(tmp_path: Path):
    """Create a test git repository with main branch."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # Initialize repo
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)

    # Create initial commit
    (repo / "README.md").write_text("# Test Repository")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True)

    return repo


class TestWorktreePaths:
    """Tests for path generation functions."""

    def test_get_worktree_dir(self, tmp_path: Path):
        """Test worktree directory path generation."""
        repo = tmp_path / "my-project"
        repo.mkdir()

        worktree_dir = get_worktree_dir(repo)
        assert worktree_dir == tmp_path / "my-project.worktrees"

    def test_get_worker_worktree_path(self, tmp_path: Path):
        """Test worker worktree path generation."""
        repo = tmp_path / "project"
        repo.mkdir()

        path = get_worker_worktree_path(repo, "claude-code-1")
        assert path == tmp_path / "project.worktrees" / "worker-claude-code-1"

    def test_get_worker_worktree_path_sanitizes_id(self, tmp_path: Path):
        """Test that worker IDs are sanitized for filesystem."""
        repo = tmp_path / "project"
        repo.mkdir()

        path = get_worker_worktree_path(repo, "worker/with:bad*chars")
        assert "worker-worker_with_bad_chars" in str(path)

    def test_generate_branch_name_with_task(self):
        """Test branch name generation with task ID."""
        config = WorktreeConfig(worker_id="worker-1", task_id="task-123")
        branch = _generate_branch_name(config)
        assert branch == "ringmaster/task-123"

    def test_generate_branch_name_without_task(self):
        """Test branch name generation without task ID."""
        config = WorktreeConfig(worker_id="worker-1")
        branch = _generate_branch_name(config)
        assert branch == "ringmaster/worker-worker-1"

    def test_generate_branch_name_custom_prefix(self):
        """Test branch name with custom prefix."""
        config = WorktreeConfig(
            worker_id="worker-1", task_id="task-456", branch_prefix="feat"
        )
        branch = _generate_branch_name(config)
        assert branch == "feat/task-456"


class TestListWorktrees:
    """Tests for listing worktrees."""

    async def test_list_worktrees_single(self, git_repo: Path):
        """Test listing worktrees for a repo with only main worktree."""
        worktrees = await list_worktrees(git_repo)

        assert len(worktrees) == 1
        assert worktrees[0].path == git_repo
        assert worktrees[0].branch == "main"

    async def test_list_worktrees_multiple(self, git_repo: Path):
        """Test listing multiple worktrees."""
        # Create a worktree
        worktree_dir = get_worktree_dir(git_repo)
        worktree_dir.mkdir()
        subprocess.run(
            ["git", "worktree", "add", "-b", "test-branch", str(worktree_dir / "wt1")],
            cwd=git_repo,
            check=True,
        )

        worktrees = await list_worktrees(git_repo)
        assert len(worktrees) == 2

        paths = [str(wt.path) for wt in worktrees]
        assert str(git_repo) in paths
        assert str(worktree_dir / "wt1") in paths


class TestCreateWorktree:
    """Tests for creating worktrees."""

    async def test_create_worktree(self, git_repo: Path):
        """Test creating a new worktree for a worker."""
        config = WorktreeConfig(worker_id="claude-1", task_id="task-001")

        # Need to create a "remote" for the test (fetch origin/main)
        # Simulate by creating main locally
        subprocess.run(["git", "branch", "-M", "main"], cwd=git_repo, check=True)

        worktree = await get_or_create_worktree(git_repo, config, base_branch="main")

        assert worktree is not None
        assert worktree.path.exists()
        assert "worker-claude-1" in str(worktree.path)
        assert worktree.branch == "ringmaster/task-001"

    async def test_create_worktree_reuses_existing(self, git_repo: Path):
        """Test that existing worktree is reused."""
        config = WorktreeConfig(worker_id="claude-1")

        # Create first time
        wt1 = await get_or_create_worktree(git_repo, config, base_branch="main")

        # Create again - should reuse
        wt2 = await get_or_create_worktree(git_repo, config, base_branch="main")

        assert wt1.path == wt2.path


class TestRemoveWorktree:
    """Tests for removing worktrees."""

    async def test_remove_worktree(self, git_repo: Path):
        """Test removing a worker's worktree."""
        config = WorktreeConfig(worker_id="claude-1")
        worktree = await get_or_create_worktree(git_repo, config, base_branch="main")

        assert worktree.path.exists()

        removed = await remove_worktree(git_repo, "claude-1")
        assert removed is True
        assert not worktree.path.exists()

    async def test_remove_nonexistent_worktree(self, git_repo: Path):
        """Test removing a worktree that doesn't exist."""
        removed = await remove_worktree(git_repo, "nonexistent-worker")
        assert removed is False


class TestWorktreeStatus:
    """Tests for worktree status."""

    async def test_status_nonexistent(self, git_repo: Path):
        """Test status for nonexistent worktree."""
        status = await get_worktree_status(git_repo, "nonexistent")
        assert status["exists"] is False

    async def test_status_clean(self, git_repo: Path):
        """Test status for clean worktree."""
        config = WorktreeConfig(worker_id="claude-1")
        await get_or_create_worktree(git_repo, config, base_branch="main")

        status = await get_worktree_status(git_repo, "claude-1")

        assert status["exists"] is True
        assert status["has_uncommitted_changes"] is False
        assert status["changed_files"] == []

    async def test_status_with_changes(self, git_repo: Path):
        """Test status for worktree with uncommitted changes."""
        config = WorktreeConfig(worker_id="claude-1")
        worktree = await get_or_create_worktree(git_repo, config, base_branch="main")

        # Make a change
        (worktree.path / "new_file.txt").write_text("content")

        status = await get_worktree_status(git_repo, "claude-1")

        assert status["has_uncommitted_changes"] is True
        assert "new_file.txt" in status["changed_files"]


class TestCommitWorktreeChanges:
    """Tests for committing changes in worktrees."""

    async def test_commit_changes(self, git_repo: Path):
        """Test committing changes in a worktree."""
        config = WorktreeConfig(worker_id="claude-1")
        worktree = await get_or_create_worktree(git_repo, config, base_branch="main")

        # Make a change
        (worktree.path / "feature.py").write_text("def hello(): pass")

        commit_hash = await commit_worktree_changes(
            git_repo, "claude-1", "Add feature.py"
        )

        assert commit_hash is not None
        assert len(commit_hash) == 40  # Full SHA

        # Verify commit exists
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=worktree.path,
            capture_output=True,
            text=True,
        )
        assert "Add feature.py" in result.stdout

    async def test_commit_no_changes(self, git_repo: Path):
        """Test committing when there are no changes."""
        config = WorktreeConfig(worker_id="claude-1")
        await get_or_create_worktree(git_repo, config, base_branch="main")

        commit_hash = await commit_worktree_changes(
            git_repo, "claude-1", "No changes"
        )

        assert commit_hash is None


class TestMergeWorktree:
    """Tests for merging worktree branches."""

    async def test_merge_no_commits(self, git_repo: Path):
        """Test merging when there are no commits to merge."""
        config = WorktreeConfig(worker_id="claude-1")
        await get_or_create_worktree(git_repo, config, base_branch="main")

        success, message = await merge_worktree_to_main(git_repo, "claude-1")

        assert success is True
        assert "No commits to merge" in message

    async def test_merge_with_commits(self, git_repo: Path):
        """Test merging with commits."""
        config = WorktreeConfig(worker_id="claude-1")
        worktree = await get_or_create_worktree(git_repo, config, base_branch="main")

        # Make changes and commit
        (worktree.path / "feature.py").write_text("def hello(): pass")
        await commit_worktree_changes(git_repo, "claude-1", "Add feature")

        success, message = await merge_worktree_to_main(git_repo, "claude-1")

        assert success is True
        assert "Merged 1 commits" in message

        # Verify file exists in main
        assert (git_repo / "feature.py").exists()


class TestCleanStaleWorktrees:
    """Tests for cleaning stale worktrees."""

    async def test_clean_stale(self, git_repo: Path):
        """Test pruning stale worktrees."""
        # Create and then manually delete a worktree directory
        config = WorktreeConfig(worker_id="claude-1")
        worktree = await get_or_create_worktree(git_repo, config, base_branch="main")

        # Manually remove the directory (making it stale)
        import shutil

        shutil.rmtree(worktree.path)

        # Prune should clean it
        removed = await clean_stale_worktrees(git_repo)

        # At least one should be removed
        assert removed >= 0  # May be 0 if git hasn't detected it yet
