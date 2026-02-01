"""Resource cleanup implementation.

Handles cleanup of:
- Git worktrees created for worker isolation
- Git branches created for tasks (ringmaster/bd-*)
- Temporary prompt/output files
- Worker scripts in /tmp
"""

import asyncio
import glob
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    success: bool
    resource_type: str  # worktree, branch, temp_file, script
    resource_path: str
    error: str | None = None


@dataclass
class CleanupStats:
    """Statistics from a cleanup run."""

    worktrees_removed: int = 0
    branches_removed: int = 0
    temp_files_removed: int = 0
    scripts_removed: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)

    def __add__(self, other: "CleanupStats") -> "CleanupStats":
        return CleanupStats(
            worktrees_removed=self.worktrees_removed + other.worktrees_removed,
            branches_removed=self.branches_removed + other.branches_removed,
            temp_files_removed=self.temp_files_removed + other.temp_files_removed,
            scripts_removed=self.scripts_removed + other.scripts_removed,
            bytes_freed=self.bytes_freed + other.bytes_freed,
            errors=self.errors + other.errors,
        )


class ResourceCleaner:
    """Cleans up resources consumed during task execution.

    Resources tracked:
    - Worktrees: /path/to/repo.worktrees/worker-{worker_id}/
    - Branches: ringmaster/bd-{task_id}
    - Temp files: /tmp/ringmaster-prompt-{task_id}.txt, /tmp/ringmaster-output-*
    - Scripts: /tmp/ringmaster-workers/worker-{worker_id}.sh
    """

    def __init__(
        self,
        repo_path: Path | None = None,
        worktree_base: Path | None = None,
        temp_dir: Path | None = None,
        script_dir: Path | None = None,
        max_worktree_age: timedelta = timedelta(hours=24),
        max_temp_age: timedelta = timedelta(hours=1),
    ):
        self.repo_path = repo_path or Path.cwd()
        self.worktree_base = worktree_base or self.repo_path.parent / f"{self.repo_path.name}.worktrees"
        self.temp_dir = temp_dir or Path("/tmp")
        self.script_dir = script_dir or Path("/tmp/ringmaster-workers")
        self.max_worktree_age = max_worktree_age
        self.max_temp_age = max_temp_age

    async def cleanup_task(self, task_id: str, worker_id: str | None = None) -> CleanupStats:
        """Clean up all resources associated with a completed task.

        Args:
            task_id: The task ID (used for branches and temp files).
            worker_id: Optional worker ID (used for worktrees).

        Returns:
            CleanupStats with counts of removed resources.
        """
        stats = CleanupStats()

        # Clean up worktree if worker_id provided
        if worker_id:
            worktree_stats = await self.cleanup_worktree(worker_id, task_id)
            stats = stats + worktree_stats

        # Clean up task branch
        branch_stats = await self.cleanup_branch(task_id)
        stats = stats + branch_stats

        # Clean up temp files
        temp_stats = await self.cleanup_temp_files(task_id)
        stats = stats + temp_stats

        return stats

    async def cleanup_worktree(self, worker_id: str, task_id: str | None = None) -> CleanupStats:
        """Remove a worker's git worktree.

        Args:
            worker_id: The worker ID.
            task_id: Optional task ID for logging.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()
        worktree_path = self.worktree_base / f"worker-{worker_id}"

        if not worktree_path.exists():
            return stats

        try:
            # Get size before removal
            size = await self._get_dir_size(worktree_path)

            # Use git worktree remove
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "remove", "--force", str(worktree_path),
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                stats.worktrees_removed = 1
                stats.bytes_freed = size
                logger.info(f"Removed worktree: {worktree_path}")
            else:
                # Try manual removal if git worktree remove fails
                error = stderr.decode().strip()
                if worktree_path.exists():
                    shutil.rmtree(worktree_path, ignore_errors=True)
                    if not worktree_path.exists():
                        stats.worktrees_removed = 1
                        stats.bytes_freed = size
                        logger.info(f"Manually removed worktree: {worktree_path}")
                    else:
                        stats.errors.append(f"Failed to remove worktree {worktree_path}: {error}")
                        logger.warning(f"Failed to remove worktree {worktree_path}: {error}")

        except Exception as e:
            stats.errors.append(f"Error removing worktree {worktree_path}: {e}")
            logger.error(f"Error removing worktree {worktree_path}: {e}")

        return stats

    async def cleanup_branch(self, task_id: str) -> CleanupStats:
        """Delete a task's git branch.

        Args:
            task_id: The task ID.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()
        branch_name = f"ringmaster/bd-{task_id}"

        try:
            # Check if branch exists
            proc = await asyncio.create_subprocess_exec(
                "git", "branch", "--list", branch_name,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if not stdout.strip():
                return stats  # Branch doesn't exist

            # Delete branch
            proc = await asyncio.create_subprocess_exec(
                "git", "branch", "-D", branch_name,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                stats.branches_removed = 1
                logger.info(f"Deleted branch: {branch_name}")
            else:
                error = stderr.decode().strip()
                stats.errors.append(f"Failed to delete branch {branch_name}: {error}")
                logger.warning(f"Failed to delete branch {branch_name}: {error}")

        except Exception as e:
            stats.errors.append(f"Error deleting branch {branch_name}: {e}")
            logger.error(f"Error deleting branch {branch_name}: {e}")

        return stats

    async def cleanup_temp_files(self, task_id: str) -> CleanupStats:
        """Remove temporary files for a task.

        Args:
            task_id: The task ID.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()

        patterns = [
            f"ringmaster-prompt-{task_id}*",
            f"ringmaster-output-{task_id}*",
        ]

        for pattern in patterns:
            for filepath in glob.glob(str(self.temp_dir / pattern)):
                try:
                    path = Path(filepath)
                    size = path.stat().st_size if path.exists() else 0
                    path.unlink()
                    stats.temp_files_removed += 1
                    stats.bytes_freed += size
                    logger.debug(f"Removed temp file: {filepath}")
                except Exception as e:
                    stats.errors.append(f"Error removing {filepath}: {e}")
                    logger.warning(f"Error removing temp file {filepath}: {e}")

        return stats

    async def cleanup_worker_script(self, worker_id: str) -> CleanupStats:
        """Remove a worker's script file.

        Args:
            worker_id: The worker ID.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()
        script_path = self.script_dir / f"worker-{worker_id}.sh"

        if not script_path.exists():
            return stats

        try:
            size = script_path.stat().st_size
            script_path.unlink()
            stats.scripts_removed = 1
            stats.bytes_freed += size
            logger.info(f"Removed worker script: {script_path}")
        except Exception as e:
            stats.errors.append(f"Error removing script {script_path}: {e}")
            logger.warning(f"Error removing worker script {script_path}: {e}")

        return stats

    async def cleanup_stale_worktrees(self) -> CleanupStats:
        """Remove worktrees older than max_worktree_age.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()

        if not self.worktree_base.exists():
            return stats

        cutoff = datetime.now(UTC) - self.max_worktree_age

        for worktree_dir in self.worktree_base.iterdir():
            if not worktree_dir.is_dir():
                continue
            if not worktree_dir.name.startswith("worker-"):
                continue

            try:
                # Check modification time
                mtime = datetime.fromtimestamp(worktree_dir.stat().st_mtime, tz=UTC)
                if mtime < cutoff:
                    worker_id = worktree_dir.name.replace("worker-", "")
                    wt_stats = await self.cleanup_worktree(worker_id)
                    stats = stats + wt_stats
            except Exception as e:
                stats.errors.append(f"Error checking worktree {worktree_dir}: {e}")

        return stats

    async def cleanup_stale_branches(self) -> CleanupStats:
        """Remove orphaned ringmaster/bd-* branches.

        A branch is orphaned if:
        - It has no associated worktree
        - The associated task is done/failed

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()

        try:
            # List all ringmaster branches
            proc = await asyncio.create_subprocess_exec(
                "git", "branch", "--list", "ringmaster/bd-*",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if proc.returncode != 0 or not stdout:
                return stats

            branches = [b.strip().lstrip("* ") for b in stdout.decode().strip().split("\n") if b.strip()]

            # List worktrees to see which branches are in use
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "list", "--porcelain",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            active_branches = set()
            for line in stdout.decode().split("\n"):
                if line.startswith("branch refs/heads/"):
                    branch = line.replace("branch refs/heads/", "")
                    active_branches.add(branch)

            # Delete orphaned branches
            for branch in branches:
                if branch not in active_branches:
                    task_id = branch.replace("ringmaster/bd-", "")
                    branch_stats = await self.cleanup_branch(task_id)
                    stats = stats + branch_stats

        except Exception as e:
            stats.errors.append(f"Error cleaning stale branches: {e}")
            logger.error(f"Error cleaning stale branches: {e}")

        return stats

    async def cleanup_stale_temp_files(self) -> CleanupStats:
        """Remove temp files older than max_temp_age.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()
        cutoff = datetime.now(UTC) - self.max_temp_age

        patterns = ["ringmaster-prompt-*", "ringmaster-output-*"]

        for pattern in patterns:
            for filepath in glob.glob(str(self.temp_dir / pattern)):
                try:
                    path = Path(filepath)
                    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        size = path.stat().st_size
                        path.unlink()
                        stats.temp_files_removed += 1
                        stats.bytes_freed += size
                        logger.debug(f"Removed stale temp file: {filepath}")
                except Exception as e:
                    stats.errors.append(f"Error removing {filepath}: {e}")

        return stats

    async def cleanup_stale_scripts(self) -> CleanupStats:
        """Remove worker scripts for workers that are no longer running.

        Returns:
            CleanupStats.
        """
        stats = CleanupStats()

        if not self.script_dir.exists():
            return stats

        # Get running tmux sessions
        proc = await asyncio.create_subprocess_exec(
            "tmux", "list-sessions", "-F", "#{session_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()

        running_workers = set()
        if proc.returncode == 0 and stdout:
            for session in stdout.decode().strip().split("\n"):
                if session.startswith("rm-worker-"):
                    worker_id = session.replace("rm-worker-", "")
                    running_workers.add(worker_id)

        # Remove scripts for non-running workers
        for script in self.script_dir.glob("worker-*.sh"):
            worker_id = script.stem.replace("worker-", "")
            if worker_id not in running_workers:
                script_stats = await self.cleanup_worker_script(worker_id)
                stats = stats + script_stats

        return stats

    async def cleanup_all_stale(self) -> CleanupStats:
        """Run all stale resource cleanup.

        Returns:
            Combined CleanupStats.
        """
        stats = CleanupStats()

        # Run cleanup in parallel
        results = await asyncio.gather(
            self.cleanup_stale_worktrees(),
            self.cleanup_stale_branches(),
            self.cleanup_stale_temp_files(),
            self.cleanup_stale_scripts(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, CleanupStats):
                stats = stats + result
            elif isinstance(result, Exception):
                stats.errors.append(str(result))

        return stats

    async def get_status(self) -> dict:
        """Get current resource usage status.

        Returns:
            Dict with resource counts and sizes.
        """
        status = {
            "worktrees": {"count": 0, "bytes": 0},
            "branches": {"count": 0},
            "temp_files": {"count": 0, "bytes": 0},
            "scripts": {"count": 0, "bytes": 0},
        }

        # Count worktrees
        if self.worktree_base.exists():
            for d in self.worktree_base.iterdir():
                if d.is_dir() and d.name.startswith("worker-"):
                    status["worktrees"]["count"] += 1
                    status["worktrees"]["bytes"] += await self._get_dir_size(d)

        # Count branches
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "branch", "--list", "ringmaster/bd-*",
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                branches = [b for b in stdout.decode().strip().split("\n") if b.strip()]
                status["branches"]["count"] = len(branches)
        except Exception:
            pass

        # Count temp files
        for pattern in ["ringmaster-prompt-*", "ringmaster-output-*"]:
            for filepath in glob.glob(str(self.temp_dir / pattern)):
                try:
                    path = Path(filepath)
                    status["temp_files"]["count"] += 1
                    status["temp_files"]["bytes"] += path.stat().st_size
                except Exception:
                    pass

        # Count scripts
        if self.script_dir.exists():
            for script in self.script_dir.glob("worker-*.sh"):
                try:
                    status["scripts"]["count"] += 1
                    status["scripts"]["bytes"] += script.stat().st_size
                except Exception:
                    pass

        return status

    async def _get_dir_size(self, path: Path) -> int:
        """Get total size of a directory in bytes."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except Exception:
            pass
        return total


# Convenience functions

async def cleanup_task_resources(task_id: str, worker_id: str | None = None) -> CleanupStats:
    """Clean up resources for a completed task.

    Args:
        task_id: The task ID.
        worker_id: Optional worker ID.

    Returns:
        CleanupStats.
    """
    cleaner = ResourceCleaner()
    return await cleaner.cleanup_task(task_id, worker_id)


async def cleanup_stale_resources() -> CleanupStats:
    """Clean up all stale resources.

    Returns:
        CleanupStats.
    """
    cleaner = ResourceCleaner()
    return await cleaner.cleanup_all_stale()
