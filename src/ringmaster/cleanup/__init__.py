"""Resource cleanup for ringmaster.

Based on ADR-016: Workers clean up consumed resources after task completion.
Handles:
- Git worktrees
- Task branches
- Temporary files
- Worker scripts
"""

from ringmaster.cleanup.cleaner import (
    ResourceCleaner,
    CleanupResult,
    CleanupStats,
    cleanup_task_resources,
    cleanup_stale_resources,
)

__all__ = [
    "ResourceCleaner",
    "CleanupResult",
    "CleanupStats",
    "cleanup_task_resources",
    "cleanup_stale_resources",
]
