"""Git operations module for file history, diff viewing, and worktree management."""

from ringmaster.git.operations import (
    DiffHunk,
    FileCommit,
    FileDiff,
    GitError,
    RevertResult,
    abort_revert,
    get_commit_info,
    get_file_at_commit,
    get_file_diff,
    get_file_history,
    is_git_repo,
    revert_commit,
    revert_file_in_commit,
    revert_to_commit,
)
from ringmaster.git.worktrees import (
    Worktree,
    WorktreeConfig,
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

__all__ = [
    # File operations
    "FileCommit",
    "FileDiff",
    "DiffHunk",
    "GitError",
    "RevertResult",
    "get_file_history",
    "get_file_diff",
    "get_file_at_commit",
    "get_commit_info",
    "is_git_repo",
    # Revert operations
    "revert_commit",
    "revert_to_commit",
    "revert_file_in_commit",
    "abort_revert",
    # Worktree management
    "Worktree",
    "WorktreeConfig",
    "list_worktrees",
    "get_worktree_dir",
    "get_worker_worktree_path",
    "get_or_create_worktree",
    "remove_worktree",
    "clean_stale_worktrees",
    "merge_worktree_to_main",
    "get_worktree_status",
    "commit_worktree_changes",
]
