"""Git worktree management for worker isolation.

Each worker gets an isolated worktree to prevent conflicts during parallel execution.
Worktrees share the .git directory with the main repository, making them lightweight.

Layout:
    /workspace/project-main/              # Main checkout (user's view)
    /workspace/project-main.worktrees/
        worker-claude-1/                  # Worktree for claude-code-1
        worker-claude-2/                  # Worktree for claude-code-2
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ringmaster.git.operations import GitError, _run_git_command

logger = logging.getLogger(__name__)


@dataclass
class Worktree:
    """Represents a git worktree."""

    path: Path
    branch: str
    commit_hash: str
    is_bare: bool = False
    is_detached: bool = False
    is_locked: bool = False
    is_prunable: bool = False


@dataclass
class WorktreeConfig:
    """Configuration for creating a worktree."""

    worker_id: str
    task_id: str | None = None
    branch_prefix: str = "ringmaster"


async def list_worktrees(repo_path: Path) -> list[Worktree]:
    """List all worktrees for a repository.

    Args:
        repo_path: Path to the main repository.

    Returns:
        List of Worktree objects.

    Raises:
        GitError: If git command fails.
    """
    args = ["worktree", "list", "--porcelain"]
    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        raise GitError(f"Failed to list worktrees: {stderr}")

    worktrees: list[Worktree] = []
    current: dict[str, str] = {}

    for line in stdout.strip().split("\n"):
        if not line:
            if current:
                worktrees.append(
                    Worktree(
                        path=Path(current.get("worktree", "")),
                        branch=current.get("branch", "").replace("refs/heads/", ""),
                        commit_hash=current.get("HEAD", ""),
                        is_bare=current.get("bare") == "bare",
                        is_detached="detached" in current,
                        is_locked="locked" in current,
                        is_prunable="prunable" in current,
                    )
                )
                current = {}
            continue

        if line.startswith("worktree "):
            current["worktree"] = line[9:]
        elif line.startswith("HEAD "):
            current["HEAD"] = line[5:]
        elif line.startswith("branch "):
            current["branch"] = line[7:]
        elif line == "bare":
            current["bare"] = "bare"
        elif line == "detached":
            current["detached"] = "detached"
        elif line.startswith("locked"):
            current["locked"] = "locked"
        elif line.startswith("prunable"):
            current["prunable"] = "prunable"

    # Handle last entry
    if current:
        worktrees.append(
            Worktree(
                path=Path(current.get("worktree", "")),
                branch=current.get("branch", "").replace("refs/heads/", ""),
                commit_hash=current.get("HEAD", ""),
                is_bare=current.get("bare") == "bare",
                is_detached="detached" in current,
                is_locked="locked" in current,
                is_prunable="prunable" in current,
            )
        )

    return worktrees


def get_worktree_dir(repo_path: Path) -> Path:
    """Get the worktrees directory for a repository.

    The worktrees directory is named <repo>.worktrees and sits alongside
    the main repository.

    Args:
        repo_path: Path to the main repository.

    Returns:
        Path to the worktrees directory.
    """
    # Use parent directory + repo name + .worktrees
    repo_name = repo_path.resolve().name
    return repo_path.parent / f"{repo_name}.worktrees"


def get_worker_worktree_path(repo_path: Path, worker_id: str) -> Path:
    """Get the worktree path for a specific worker.

    Args:
        repo_path: Path to the main repository.
        worker_id: The worker's ID.

    Returns:
        Path where the worker's worktree should be.
    """
    worktree_dir = get_worktree_dir(repo_path)
    # Sanitize worker_id for filesystem
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", worker_id)
    return worktree_dir / f"worker-{safe_id}"


async def get_or_create_worktree(
    repo_path: Path,
    config: WorktreeConfig,
    base_branch: str = "main",
) -> Worktree:
    """Get an existing worktree for a worker or create a new one.

    Each worker gets a dedicated worktree. The worktree is created on a
    unique branch for the task being executed.

    Args:
        repo_path: Path to the main repository.
        config: Worktree configuration.
        base_branch: Branch to create the worktree from (default: main).

    Returns:
        Worktree object for the worker.

    Raises:
        GitError: If git operations fail.
    """
    worktree_path = get_worker_worktree_path(repo_path, config.worker_id)

    # Check if worktree already exists
    existing = await list_worktrees(repo_path)
    for wt in existing:
        if wt.path == worktree_path:
            logger.info(f"Using existing worktree at {worktree_path}")
            # Update to a fresh branch for the new task if needed
            if config.task_id:
                await _update_worktree_branch(
                    repo_path, worktree_path, config, base_branch
                )
                # Re-fetch to get updated info
                updated = await list_worktrees(repo_path)
                for uwt in updated:
                    if uwt.path == worktree_path:
                        return uwt
            return wt

    # Create worktrees directory
    worktree_dir = get_worktree_dir(repo_path)
    worktree_dir.mkdir(parents=True, exist_ok=True)

    # Generate branch name
    branch_name = _generate_branch_name(config)

    # Create the worktree
    logger.info(f"Creating worktree at {worktree_path} on branch {branch_name}")

    # Determine the base reference to use
    # Try origin/<branch> first (for repos with remotes), fallback to local branch
    base_ref = await _get_base_ref(repo_path, base_branch)

    # Create the worktree with a new branch
    args = [
        "worktree",
        "add",
        "-b",
        branch_name,
        str(worktree_path),
        base_ref,
    ]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        # Branch might already exist, try without -b
        if "already exists" in stderr:
            args = ["worktree", "add", str(worktree_path), branch_name]
            stdout, stderr, rc = await _run_git_command(args, repo_path)

        if rc != 0:
            raise GitError(f"Failed to create worktree: {stderr}")

    # Get the created worktree
    worktrees = await list_worktrees(repo_path)
    for wt in worktrees:
        if wt.path == worktree_path:
            return wt

    raise GitError(f"Worktree created but not found at {worktree_path}")


async def _update_worktree_branch(
    repo_path: Path,
    worktree_path: Path,
    config: WorktreeConfig,
    base_branch: str,
) -> None:
    """Update a worktree to a fresh branch for a new task.

    This resets the worktree to the latest base branch and creates
    a new branch for the task.

    Args:
        repo_path: Path to the main repository.
        worktree_path: Path to the worktree.
        config: Worktree configuration with task info.
        base_branch: Branch to reset to.
    """
    # Determine the base reference to use
    base_ref = await _get_base_ref(repo_path, base_branch)

    # Generate new branch name for this task
    branch_name = _generate_branch_name(config)

    # Clean up any uncommitted changes
    await _run_git_command(["reset", "--hard"], worktree_path)
    await _run_git_command(["clean", "-fd"], worktree_path)

    # Create and checkout new branch from latest base
    args = ["checkout", "-B", branch_name, base_ref]
    stdout, stderr, rc = await _run_git_command(args, worktree_path)

    if rc != 0:
        raise GitError(f"Failed to update worktree branch: {stderr}")

    logger.info(f"Updated worktree to branch {branch_name}")


async def _get_base_ref(repo_path: Path, base_branch: str) -> str:
    """Determine the best base reference for creating a worktree.

    Tries to use origin/<branch> if available, otherwise falls back
    to the local branch.

    Args:
        repo_path: Path to the repository.
        base_branch: The branch name to base off.

    Returns:
        The ref string to use (e.g., "origin/main" or "main").
    """
    # Check if origin remote exists
    stdout, stderr, rc = await _run_git_command(["remote"], repo_path)
    has_origin = "origin" in stdout.split()

    if has_origin:
        # Try to fetch from origin
        stdout, stderr, rc = await _run_git_command(
            ["fetch", "origin", base_branch], repo_path
        )
        if rc == 0:
            return f"origin/{base_branch}"

    # Fall back to local branch
    return base_branch


def _generate_branch_name(config: WorktreeConfig) -> str:
    """Generate a branch name for a worker's task.

    Format: ringmaster/<task-id> or ringmaster/<worker-id> if no task

    Args:
        config: Worktree configuration.

    Returns:
        Branch name string.
    """
    if config.task_id:
        # Sanitize task_id
        safe_task = re.sub(r"[^a-zA-Z0-9_-]", "_", config.task_id)
        return f"{config.branch_prefix}/{safe_task}"
    else:
        safe_worker = re.sub(r"[^a-zA-Z0-9_-]", "_", config.worker_id)
        return f"{config.branch_prefix}/worker-{safe_worker}"


async def remove_worktree(repo_path: Path, worker_id: str, force: bool = False) -> bool:
    """Remove a worker's worktree.

    Args:
        repo_path: Path to the main repository.
        worker_id: The worker's ID.
        force: Force removal even with uncommitted changes.

    Returns:
        True if removed, False if worktree didn't exist.

    Raises:
        GitError: If removal fails.
    """
    worktree_path = get_worker_worktree_path(repo_path, worker_id)

    # Check if it exists
    existing = await list_worktrees(repo_path)
    found = any(wt.path == worktree_path for wt in existing)

    if not found:
        return False

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(worktree_path))

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        raise GitError(f"Failed to remove worktree: {stderr}")

    logger.info(f"Removed worktree at {worktree_path}")
    return True


async def clean_stale_worktrees(repo_path: Path) -> int:
    """Remove stale worktrees (those marked as prunable).

    Args:
        repo_path: Path to the main repository.

    Returns:
        Number of worktrees removed.

    Raises:
        GitError: If pruning fails.
    """
    args = ["worktree", "prune", "-v"]
    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        raise GitError(f"Failed to prune worktrees: {stderr}")

    # Count removed worktrees from verbose output
    removed = 0
    for line in stdout.split("\n"):
        if "Removing" in line:
            removed += 1

    if removed:
        logger.info(f"Pruned {removed} stale worktrees")

    return removed


async def merge_worktree_to_main(
    repo_path: Path,
    worker_id: str,
    target_branch: str = "main",
    merge_message: str | None = None,
) -> tuple[bool, str]:
    """Merge a worker's worktree branch into the target branch.

    Args:
        repo_path: Path to the main repository.
        worker_id: The worker's ID.
        target_branch: Branch to merge into (default: main).
        merge_message: Custom merge commit message.

    Returns:
        Tuple of (success, message/error).

    Raises:
        GitError: If git operations fail.
    """
    worktree_path = get_worker_worktree_path(repo_path, worker_id)

    # Get the current branch in the worktree
    stdout, stderr, rc = await _run_git_command(
        ["rev-parse", "--abbrev-ref", "HEAD"], worktree_path
    )
    if rc != 0:
        raise GitError(f"Failed to get current branch: {stderr}")

    source_branch = stdout.strip()

    # Check if there are any commits to merge
    stdout, stderr, rc = await _run_git_command(
        ["rev-list", "--count", f"{target_branch}..{source_branch}"], worktree_path
    )
    if rc != 0:
        raise GitError(f"Failed to count commits: {stderr}")

    commit_count = int(stdout.strip())
    if commit_count == 0:
        return True, "No commits to merge"

    # Switch to main repo and merge
    # First, fetch the worktree branch
    await _run_git_command(["fetch", ".", f"{source_branch}:{source_branch}"], repo_path)

    # Checkout target branch
    await _run_git_command(["checkout", target_branch], repo_path)

    # Merge the worker's branch
    msg = merge_message or f"Merge {source_branch} from worker {worker_id}"
    args = ["merge", "--no-ff", "-m", msg, source_branch]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        if "CONFLICT" in stdout or "conflict" in stderr.lower():
            return False, f"Merge conflict: {stderr}"
        raise GitError(f"Failed to merge: {stderr}")

    return True, f"Merged {commit_count} commits from {source_branch}"


async def get_worktree_status(repo_path: Path, worker_id: str) -> dict:
    """Get the status of a worker's worktree.

    Returns information about uncommitted changes, branch, and commits ahead/behind.

    Args:
        repo_path: Path to the main repository.
        worker_id: The worker's ID.

    Returns:
        Dictionary with status information.

    Raises:
        GitError: If git operations fail.
    """
    worktree_path = get_worker_worktree_path(repo_path, worker_id)

    if not worktree_path.exists():
        return {"exists": False}

    # Get current branch
    stdout, stderr, rc = await _run_git_command(
        ["rev-parse", "--abbrev-ref", "HEAD"], worktree_path
    )
    branch = stdout.strip() if rc == 0 else "unknown"

    # Get status (uncommitted changes)
    stdout, stderr, rc = await _run_git_command(
        ["status", "--porcelain"], worktree_path
    )
    has_changes = bool(stdout.strip()) if rc == 0 else False

    # Count uncommitted files
    changed_files = []
    if stdout.strip():
        changed_files = [
            line[3:] for line in stdout.strip().split("\n") if line
        ]

    # Get commits ahead of main
    stdout, stderr, rc = await _run_git_command(
        ["rev-list", "--count", f"main..{branch}"], worktree_path
    )
    commits_ahead = int(stdout.strip()) if rc == 0 else 0

    return {
        "exists": True,
        "path": str(worktree_path),
        "branch": branch,
        "has_uncommitted_changes": has_changes,
        "changed_files": changed_files,
        "commits_ahead": commits_ahead,
    }


async def commit_worktree_changes(
    repo_path: Path,
    worker_id: str,
    message: str,
    add_all: bool = True,
) -> str | None:
    """Commit changes in a worker's worktree.

    Args:
        repo_path: Path to the main repository.
        worker_id: The worker's ID.
        message: Commit message.
        add_all: If True, add all changes before committing.

    Returns:
        Commit hash if successful, None if no changes to commit.

    Raises:
        GitError: If git operations fail.
    """
    worktree_path = get_worker_worktree_path(repo_path, worker_id)

    if add_all:
        # Stage all changes
        await _run_git_command(["add", "-A"], worktree_path)

    # Check if there's anything to commit
    stdout, stderr, rc = await _run_git_command(
        ["status", "--porcelain"], worktree_path
    )

    if not stdout.strip():
        return None  # Nothing to commit

    # Commit
    args = ["commit", "-m", message]
    stdout, stderr, rc = await _run_git_command(args, worktree_path)

    if rc != 0:
        raise GitError(f"Failed to commit: {stderr}")

    # Get the commit hash
    stdout, stderr, rc = await _run_git_command(["rev-parse", "HEAD"], worktree_path)
    if rc != 0:
        raise GitError(f"Failed to get commit hash: {stderr}")

    return stdout.strip()
