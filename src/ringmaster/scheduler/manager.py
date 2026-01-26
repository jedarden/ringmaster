"""Scheduler for managing worker lifecycles and task execution.

Based on docs/06-deployment.md:
- Process supervision and health monitoring
- Worker lifecycle management
- Hot-reload support
- Self-improvement safety rails
"""

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

from ringmaster.db import Database, TaskRepository, WorkerRepository
from ringmaster.domain import Task, TaskStatus, Worker, WorkerStatus
from ringmaster.queue import QueueManager
from ringmaster.worker import WorkerExecutor

logger = logging.getLogger(__name__)


class Scheduler:
    """Scheduler for orchestrating worker execution.

    Responsibilities:
    - Monitor queue for ready tasks
    - Assign tasks to idle workers
    - Execute tasks using WorkerExecutor
    - Handle completion/failure lifecycle
    - Health monitoring and recovery
    """

    def __init__(
        self,
        db: Database,
        poll_interval: float = 2.0,
        max_concurrent_tasks: int = 4,
        output_dir: Path | None = None,
    ):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.worker_repo = WorkerRepository(db)
        self.queue_manager = QueueManager(db)
        self.executor = WorkerExecutor(db, output_dir=output_dir)

        self.poll_interval = poll_interval
        self.max_concurrent_tasks = max_concurrent_tasks

        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._health_check_interval = 30.0  # seconds

    async def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        logger.info("Scheduler starting...")

        # Start background tasks
        asyncio.create_task(self._assignment_loop())
        asyncio.create_task(self._health_check_loop())

        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._running = False
        logger.info("Scheduler stopping...")

        # Cancel all running tasks
        for _task_id, task in list(self._tasks.items()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Mark all busy workers as offline
        busy_workers = await self.worker_repo.list(status=WorkerStatus.BUSY)
        for worker in busy_workers:
            worker.status = WorkerStatus.OFFLINE
            worker.current_task_id = None
            await self.worker_repo.update(worker)

        logger.info("Scheduler stopped")

    async def _assignment_loop(self) -> None:
        """Main loop for assigning tasks to workers."""
        while self._running:
            try:
                await self._process_assignments()
            except Exception as e:
                logger.error(f"Assignment loop error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _process_assignments(self) -> None:
        """Process pending task assignments."""
        # Check capacity
        current_tasks = len(self._tasks)
        if current_tasks >= self.max_concurrent_tasks:
            return

        # Get idle workers
        idle_workers = await self.worker_repo.get_idle_workers()
        if not idle_workers:
            return

        # Get ready tasks
        ready_tasks = await self.task_repo.get_ready_tasks()
        if not ready_tasks:
            return

        # Assign tasks up to capacity
        available_slots = self.max_concurrent_tasks - current_tasks
        for worker in idle_workers[:available_slots]:
            if not ready_tasks:
                break

            task = ready_tasks.pop(0)
            await self._start_task_execution(task, worker)

    async def _start_task_execution(self, task: Task, worker: Worker) -> None:
        """Start executing a task with a worker."""
        logger.info(f"Starting task {task.id} with worker {worker.id}")

        # Create execution task
        async def execute() -> None:
            try:
                result = await self.executor.execute_task(task, worker)
                logger.info(f"Task {task.id} completed: {result.status}")

                # Handle completion
                if result.success:
                    await self.queue_manager.complete_task(
                        task.id, success=True, output_path=task.output_path
                    )
                else:
                    await self.queue_manager.complete_task(
                        task.id, success=False, output_path=task.output_path
                    )

            except asyncio.CancelledError:
                logger.info(f"Task {task.id} was cancelled")
                # Reset task status
                task.status = TaskStatus.READY
                task.worker_id = None
                await self.task_repo.update_task(task)
                raise

            except Exception as e:
                logger.error(f"Task {task.id} execution error: {e}")
                await self.queue_manager.complete_task(task.id, success=False)

            finally:
                self._tasks.pop(task.id, None)

        # Store and start the task
        execution_task = asyncio.create_task(execute())
        self._tasks[task.id] = execution_task

    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        while self._running:
            try:
                await self._perform_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self._health_check_interval)

    async def _perform_health_checks(self) -> None:
        """Perform health checks on workers and tasks."""
        # Check for stuck tasks
        stuck_threshold = datetime.utcnow() - timedelta(hours=2)
        in_progress = await self.task_repo.list_tasks(status=TaskStatus.IN_PROGRESS)

        for task in in_progress:
            if not isinstance(task, Task):
                continue
            if task.started_at and task.started_at < stuck_threshold:
                logger.warning(f"Task {task.id} appears stuck (started {task.started_at})")
                # Could implement automatic recovery here

        # Check for workers with stale status
        busy_workers = await self.worker_repo.list(status=WorkerStatus.BUSY)
        for worker in busy_workers:
            if worker.current_task_id and worker.current_task_id not in self._tasks:
                logger.warning(f"Worker {worker.id} marked busy but task not running")
                worker.status = WorkerStatus.IDLE
                worker.current_task_id = None
                await self.worker_repo.update(worker)

    async def get_status(self) -> dict:
        """Get scheduler status."""
        stats = await self.queue_manager.get_queue_stats()
        return {
            "running": self._running,
            "active_tasks": list(self._tasks.keys()),
            "active_task_count": len(self._tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "queue_stats": stats,
        }

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id not in self._tasks:
            return False

        self._tasks[task_id].cancel()
        return True
