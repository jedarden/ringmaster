"""Queue manager for task assignment and lifecycle."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from ringmaster.db import Database, TaskRepository, WorkerRepository
from ringmaster.domain import Task, TaskStatus, Worker, WorkerStatus
from ringmaster.queue.priority import PriorityCalculator

logger = logging.getLogger(__name__)


class QueueManager:
    """Manages the task queue and worker assignments.

    Responsibilities:
    - Maintain priority-ordered queue of ready tasks
    - Assign tasks to available workers
    - Handle task completion and failure
    - Trigger priority recalculation on graph changes
    """

    def __init__(self, db: Database):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.worker_repo = WorkerRepository(db)
        self.priority_calc = PriorityCalculator(db)
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the queue manager loop."""
        self._running = True
        logger.info("Queue manager started")

        while self._running:
            try:
                await self._process_queue()
            except Exception as e:
                logger.error(f"Queue processing error: {e}")

            await asyncio.sleep(1)  # Poll interval

    async def stop(self) -> None:
        """Stop the queue manager."""
        self._running = False
        logger.info("Queue manager stopped")

    async def _process_queue(self) -> None:
        """Process the queue: assign ready tasks to idle workers."""
        async with self._lock:
            # Get idle workers
            idle_workers = await self.worker_repo.get_idle_workers()
            if not idle_workers:
                return

            # Get ready tasks (dependencies satisfied)
            ready_tasks = await self.task_repo.get_ready_tasks()
            if not ready_tasks:
                return

            # Assign tasks to workers
            for worker in idle_workers:
                if not ready_tasks:
                    break

                # Get highest priority task
                task = ready_tasks.pop(0)
                await self._assign_task(task, worker)

    async def _assign_task(self, task: Task, worker: Worker) -> None:
        """Assign a task to a worker."""
        # Check if task has exceeded max iterations (needs escalation)
        if task.iteration >= task.max_iterations:
            logger.warning(
                f"Task {task.id} has reached max iterations ({task.iteration}/{task.max_iterations}), "
                "needs human review - marking as blocked"
            )
            task.status = TaskStatus.BLOCKED
            task.updated_at = datetime.now(UTC)
            await self.task_repo.update_task(task)
            await self._log_event("task_escalated", "task", task.id, {
                "iteration": task.iteration,
                "max_iterations": task.max_iterations,
                "reason": "max_iterations_reached",
            })
            return

        logger.info(f"Assigning task {task.id} to worker {worker.id}")

        # Update task
        task.status = TaskStatus.ASSIGNED
        task.worker_id = worker.id
        task.updated_at = datetime.now(UTC)
        await self.task_repo.update_task(task)

        # Update worker
        worker.status = WorkerStatus.BUSY
        worker.current_task_id = task.id
        worker.last_active_at = datetime.now(UTC)
        await self.worker_repo.update(worker)

        # Log event
        await self._log_event("task_assigned", "task", task.id, {
            "worker_id": worker.id,
            "priority_score": task.combined_priority,
            "iteration": task.iteration,
        })

    async def enqueue_task(self, task_id: str) -> bool:
        """Mark a task as ready for assignment.

        Returns True if task was enqueued, False if dependencies not met.
        """
        task = await self.task_repo.get_task(task_id)
        if not task or not isinstance(task, Task):
            return False

        # Check dependencies
        deps = await self.task_repo.get_dependencies(task_id)
        for dep in deps:
            dep_task = await self.task_repo.get_task(dep.parent_id)
            if dep_task and dep_task.status != TaskStatus.DONE:
                logger.debug(f"Task {task_id} blocked by dependency {dep.parent_id}")
                return False

        # Mark as ready
        task.status = TaskStatus.READY
        task.updated_at = datetime.now(UTC)
        await self.task_repo.update_task(task)

        logger.info(f"Task {task_id} enqueued")
        return True

    async def complete_task(
        self,
        task_id: str,
        success: bool = True,
        output_path: str | None = None,
    ) -> None:
        """Mark a task as complete or failed."""
        task = await self.task_repo.get_task(task_id)
        if not task or not isinstance(task, Task):
            logger.warning(f"Cannot complete task {task_id}: task not found")
            return

        worker = None
        if task.worker_id:
            worker = await self.worker_repo.get(task.worker_id)
            if not worker:
                logger.warning(f"Cannot find worker {task.worker_id} for task {task_id}")

        if success:
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now(UTC)
            if worker:
                worker.tasks_completed += 1
        else:
            task.attempts += 1
            if task.attempts >= task.max_attempts:
                task.status = TaskStatus.FAILED
            else:
                task.status = TaskStatus.READY  # Retry
            if worker:
                worker.tasks_failed += 1

        task.output_path = output_path
        task.worker_id = None
        task.updated_at = datetime.now(UTC)
        await self.task_repo.update_task(task)

        if worker:
            worker.status = WorkerStatus.IDLE
            worker.current_task_id = None
            worker.last_active_at = datetime.now(UTC)
            await self.worker_repo.update(worker)

        # Check if any blocked tasks can now be enqueued
        if success:
            dependents = await self.task_repo.get_dependents(task_id)
            for dep in dependents:
                await self.enqueue_task(dep.child_id)

        await self._log_event(
            "task_completed" if success else "task_failed",
            "task",
            task_id,
            {"attempts": task.attempts, "success": success},
        )

    async def recalculate_project_priorities(self, project_id: UUID) -> int:
        """Recalculate priorities for all tasks in a project."""
        return await self.priority_calc.recalculate_priorities(project_id)

    async def _log_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        data: dict | None = None,
    ) -> None:
        """Log an event to the events table."""
        import json

        await self.db.execute(
            """
            INSERT INTO events (event_type, entity_type, entity_id, data)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, entity_type, entity_id, json.dumps(data) if data else None),
        )
        await self.db.commit()

    async def increment_iteration(self, task_id: str) -> bool:
        """Increment the iteration count for a task.

        Called when a task completes one cycle through the work loop
        (Ralph Wiggum loop) but needs additional iterations.

        Returns True if the task can continue, False if max iterations reached.
        """
        task = await self.task_repo.get_task(task_id)
        if not task or not isinstance(task, Task):
            return False

        task.iteration += 1
        task.updated_at = datetime.now(UTC)

        if task.iteration >= task.max_iterations:
            # Task has reached max iterations - escalate
            logger.warning(
                f"Task {task_id} reached max iterations ({task.iteration}/{task.max_iterations})"
            )
            await self.task_repo.update_task(task)
            await self._log_event("iteration_limit_reached", "task", task_id, {
                "iteration": task.iteration,
                "max_iterations": task.max_iterations,
            })
            return False

        await self.task_repo.update_task(task)
        await self._log_event("iteration_incremented", "task", task_id, {
            "iteration": task.iteration,
            "max_iterations": task.max_iterations,
        })
        return True

    async def get_tasks_needing_escalation(self, project_id: UUID | None = None) -> list[Task]:
        """Get tasks that have reached max iterations and need human review.

        These tasks should be reviewed by a human to either:
        - Adjust the task scope
        - Provide additional context
        - Accept the partial progress
        - Mark as infeasible
        """
        conditions = [
            "type IN ('task', 'subtask')",
            "iteration >= max_iterations",
            "status NOT IN ('done', 'failed')",
        ]
        params: list = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))

        query = f"""
            SELECT * FROM tasks
            WHERE {' AND '.join(conditions)}
            ORDER BY combined_priority DESC
        """

        rows = await self.db.fetchall(query, tuple(params))
        return [self.task_repo._row_to_task(row) for row in rows]  # type: ignore

    async def get_queue_stats(self) -> dict:
        """Get current queue statistics."""
        ready = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM tasks WHERE status = 'ready'"
        )
        assigned = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM tasks WHERE status = 'assigned'"
        )
        in_progress = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM tasks WHERE status = 'in_progress'"
        )
        idle_workers = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status = 'idle'"
        )
        busy_workers = await self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status = 'busy'"
        )

        return {
            "ready_tasks": ready["count"] if ready else 0,
            "assigned_tasks": assigned["count"] if assigned else 0,
            "in_progress_tasks": in_progress["count"] if in_progress else 0,
            "idle_workers": idle_workers["count"] if idle_workers else 0,
            "busy_workers": busy_workers["count"] if busy_workers else 0,
        }
