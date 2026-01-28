"""
Priority Inheritance System

Implements priority inheritance where blocked tasks cause their
blockers to inherit higher priority scores.
"""

import logging

from ringmaster.db import Database, DependencyRepository, TaskRepository
from ringmaster.domain import TaskStatus

logger = logging.getLogger(__name__)


class PriorityInheritance:
    """
    Manages priority inheritance for blocked tasks.

    When task A blocks task B, and B has a higher priority score,
    A inherits B's priority to unblock the critical path.
    """

    def __init__(self, db: Database):
        """
        Initialize the priority inheritance system.

        Args:
            db: Database connection
        """
        self.db = db
        self._task_repo: TaskRepository | None = None
        self._dep_repo: DependencyRepository | None = None

    async def recalculate_priorities(
        self,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> int:
        """
        Recalculate priorities with inheritance.

        Args:
            project_id: Scope to specific project (None = all projects)
            task_id: Triggered by specific task change (None = full recalculation)

        Returns:
            Number of priority updates made
        """
        async with self.db.get_connection() as conn:
            self._task_repo = TaskRepository(conn)
            self._dep_repo = DependencyRepository(conn)

            updates = 0

            if task_id:
                # Targeted recalculation: find tasks this task affects
                updates = await self._recalculate_for_task(task_id)
            elif project_id:
                # Project-wide recalculation
                updates = await self._recalculate_for_project(project_id)
            else:
                # Full recalculation across all projects
                updates = await self._recalculate_all()

            if updates > 0:
                logger.info(f"Priority inheritance: {updates} priority updates")

            return updates

    async def _recalculate_for_task(self, task_id: str) -> int:
        """
        Recalculate priorities for tasks affected by a specific task.

        If the task changed priority, propagate to its blockers.
        If the task changed status, recalculate dependent chains.
        """
        task = await self._task_repo.get(task_id)
        if not task:
            return 0

        updates = 0

        # Case 1: Task is blocked - check if its blockers should inherit priority
        if task.status == TaskStatus.BLOCKED:
            # Get tasks blocking this one
            blockers = await self._dep_repo.get_dependencies(task_id)

            for blocker in blockers:
                if blocker.priority_score < task.priority_score:
                    logger.debug(
                        f"Priority inheritance: {blocker.id} "
                        f"({blocker.priority_score:.2f} -> {task.priority_score:.2f}) "
                        f"blocking {task.id}"
                    )
                    await self._task_repo.update_priority(
                        blocker.id,
                        task.priority_score,
                        reason=f"Blocking task {task.id}",
                    )
                    updates += 1

        # Case 2: Task priority changed - propagate to its blockers
        # (Handled by the same logic as Case 1)

        # Case 3: Task is now done - recalculate priorities of its blockers
        if task.status == TaskStatus.DONE:
            # Find tasks that were blocked by this task
            # and see if their blockers still need elevated priority
            await self._recalculate_for_project(task.project_id)

        return updates

    async def _recalculate_for_project(self, project_id: str) -> int:
        """
        Recalculate priorities for all tasks in a project.

        Builds the dependency graph and propagates priorities
        from blocked tasks to their blockers.
        """
        updates = 0

        # Get all blocked tasks in the project
        blocked_tasks = await self._task_repo.list(
            project_id=project_id,
            status=TaskStatus.BLOCKED,
        )

        for task in blocked_tasks:
            # Get blockers for this task
            blockers = await self._dep_repo.get_dependencies(task.id)

            for blocker in blockers:
                # Only inherit if blocker has lower priority
                if blocker.priority_score < task.priority_score:
                    # Check if this blocker is already elevated
                    current = await self._task_repo.get(blocker.id)
                    if current and current.priority_score < task.priority_score:
                        logger.debug(
                            f"Priority inheritance: {blocker.id} "
                            f"inherits {task.priority_score:.2f} "
                            f"(blocking {task.id})"
                        )
                        await self._task_repo.update_priority(
                            blocker.id,
                            task.priority_score,
                            reason=f"Blocking task {task.id}",
                        )
                        updates += 1

        return updates

    async def _recalculate_all(self) -> int:
        """Recalculate priorities across all projects."""
        updates = 0

        # Get all blocked tasks
        blocked_tasks = await self._task_repo.list(
            status=TaskStatus.BLOCKED,
        )

        for task in blocked_tasks:
            updates += await self._recalculate_for_task(task.id)

        return updates

    async def get_priority_chain(self, task_id: str) -> list[dict]:
        """
        Get the priority chain for a task.

        Returns a list showing how priority is inherited
        through the dependency graph.

        Args:
            task_id: Task to analyze

        Returns:
            List of dicts with chain information
        """
        async with self.db.get_connection() as conn:
            self._task_repo = TaskRepository(conn)
            self._dep_repo = DependencyRepository(conn)

        chain = []
        visited = set()

        await self._build_chain(task_id, chain, visited)

        return chain

    async def _build_chain(
        self,
        task_id: str,
        chain: list[dict],
        visited: set[str],
    ) -> None:
        """Recursively build the priority chain."""
        if task_id in visited:
            return

        visited.add(task_id)

        task = await self._task_repo.get(task_id)
        if not task:
            return

        # Add current task to chain
        chain.append({
            "id": task.id,
            "title": task.title,
            "priority_score": task.priority_score,
            "status": task.status.value,
        })

        # If blocked, add blockers
        if task.status == TaskStatus.BLOCKED:
            blockers = await self._dep_repo.get_dependencies(task_id)
            for blocker in blockers:
                await self._build_chain(blocker.id, chain, visited)


async def trigger_priority_inheritance(
    task_id: str,
    db: Database,
) -> int:
    """
    Trigger priority inheritance recalculation for a task.

    This should be called when:
    - A task's priority changes
    - A task's status changes to/from BLOCKED
    - A dependency is added/removed

    Args:
        task_id: Task that triggered the recalculation
        db: Database connection

    Returns:
        Number of priority updates made
    """
    system = PriorityInheritance(db)
    return await system.recalculate_priorities(task_id=task_id)
