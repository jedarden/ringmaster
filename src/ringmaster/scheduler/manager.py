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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ringmaster import __version__
from ringmaster.db import Database, TaskRepository, WorkerRepository
from ringmaster.domain import Task, TaskStatus, Worker, WorkerStatus
from ringmaster.events import EventBus, EventType
from ringmaster.queue import QueueManager
from ringmaster.reload import FileChangeWatcher, HotReloader, ReloadResult
from ringmaster.reload.reloader import ReloadStatus
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
    - Self-improvement flywheel with hot-reload
    """

    def __init__(
        self,
        db: Database,
        poll_interval: float = 2.0,
        max_concurrent_tasks: int = 4,
        output_dir: Path | None = None,
        project_root: Path | None = None,
        event_bus: EventBus | None = None,
        enable_hot_reload: bool = True,
    ):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.worker_repo = WorkerRepository(db)
        self.queue_manager = QueueManager(db)
        self.executor = WorkerExecutor(
            db, output_dir=output_dir, project_dir=project_root, event_bus=event_bus
        )

        self.poll_interval = poll_interval
        self.max_concurrent_tasks = max_concurrent_tasks
        self.project_root = project_root or Path.cwd()
        self.event_bus = event_bus

        self._running = False
        self._tasks: dict[str, asyncio.Task] = {}
        self._health_check_interval = 30.0  # seconds

        # Hot-reload for self-improvement flywheel
        self.enable_hot_reload = enable_hot_reload
        self._hot_reloader: HotReloader | None = None
        self._file_watcher: FileChangeWatcher | None = None

        if enable_hot_reload:
            self._setup_hot_reload()

    def _setup_hot_reload(self) -> None:
        """Initialize hot-reload components."""
        src_dir = self.project_root / "src"
        venv_python = self.project_root / ".venv" / "bin" / "python"

        self._hot_reloader = HotReloader(
            project_root=self.project_root,
            venv_python=venv_python if venv_python.exists() else None,
        )

        self._file_watcher = FileChangeWatcher(
            watch_dirs=[src_dir],
            patterns=["*.py"],
        )
        self._file_watcher.initialize()

        logger.info(f"Hot-reload initialized for self-improvement flywheel (ringmaster v{__version__})")

    def _is_self_improvement_task(self, task: Task) -> bool:
        """Check if task modifies Ringmaster's own source code.

        A task is a self-improvement task if it modifies files in:
        - src/ringmaster/
        - tests/

        Args:
            task: The completed task to check.

        Returns:
            True if this is a self-improvement task.
        """
        if not task.output_path:
            return False

        # Check file watcher for any changes in src/ringmaster
        if self._file_watcher:
            changes = self._file_watcher.detect_changes()
            if changes:
                # Any change to ringmaster source is a self-improvement
                for change in changes:
                    if "ringmaster" in str(change.path):
                        logger.info(
                            f"Detected self-improvement: {change.change_type} {change.path}"
                        )
                        return True

        return False

    async def _handle_self_improvement(self, task: Task) -> ReloadResult | None:
        """Handle hot-reload after a self-improvement task.

        Flow:
        1. Detect modified files
        2. Validate safety (protected files, test coverage)
        3. Run tests
        4. If tests pass: reload affected modules
        5. If tests fail: rollback changes

        Args:
            task: The completed self-improvement task.

        Returns:
            ReloadResult describing outcome, or None if not applicable.
        """
        if not self._hot_reloader or not self._file_watcher:
            return None

        logger.info(f"Processing self-improvement for task {task.id}")

        # Get detected changes
        changes = self._file_watcher.detect_changes()
        if not changes:
            logger.info("No file changes detected for hot-reload")
            return None

        # Process through hot-reloader
        result = await self._hot_reloader.process_changes(changes)

        # Emit event
        if self.event_bus:
            await self.event_bus.emit(
                EventType.SCHEDULER_RELOAD,
                {
                    "task_id": task.id,
                    "status": result.status.value,
                    "reloaded_modules": result.reloaded_modules,
                    "error": result.error_message,
                },
            )

        # Log outcome
        if result.status == ReloadStatus.SUCCESS:
            logger.info(
                f"Self-improvement applied: {len(result.reloaded_modules)} modules reloaded"
            )
        elif result.status == ReloadStatus.ROLLED_BACK:
            logger.warning(f"Self-improvement rolled back: {result.error_message}")
        else:
            logger.error(f"Self-improvement failed: {result.status.value}")

        return result

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
        """Process pending task assignments.

        Uses capability matching to assign tasks to qualified workers:
        - Workers must have ALL capabilities required by a task
        - Tasks without required_capabilities can be assigned to any worker
        """
        # Check capacity
        current_tasks = len(self._tasks)
        if current_tasks >= self.max_concurrent_tasks:
            return

        # Get ready tasks
        ready_tasks = await self.task_repo.get_ready_tasks()
        if not ready_tasks:
            return

        # Assign tasks up to capacity
        available_slots = self.max_concurrent_tasks - current_tasks
        assigned_count = 0

        for task in ready_tasks:
            if assigned_count >= available_slots:
                break

            # Get task's required capabilities
            required_caps = getattr(task, "required_capabilities", [])

            # Find a capable worker for this task
            capable_workers = await self.worker_repo.get_capable_workers(required_caps)
            if not capable_workers:
                # No worker with required capabilities is available
                logger.debug(
                    f"No capable worker for task {task.id} "
                    f"(requires: {required_caps})"
                )
                continue

            # Assign to first capable worker
            worker = capable_workers[0]
            await self._start_task_execution(task, worker)
            assigned_count += 1

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

                    # Check for self-improvement (flywheel)
                    if self.enable_hot_reload and self._is_self_improvement_task(task):
                        reload_result = await self._handle_self_improvement(task)
                        if reload_result and reload_result.status == ReloadStatus.ROLLED_BACK:
                            # Task succeeded but changes rolled back due to test failure
                            logger.warning(
                                f"Task {task.id} completed but changes rolled back"
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
        stuck_threshold = datetime.now(UTC) - timedelta(hours=2)
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
        status = {
            "running": self._running,
            "active_tasks": list(self._tasks.keys()),
            "active_task_count": len(self._tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "queue_stats": stats,
            "hot_reload_enabled": self.enable_hot_reload,
        }

        # Add hot-reload history if enabled
        if self._hot_reloader:
            history = self._hot_reloader.get_reload_history(limit=5)
            status["recent_reloads"] = [
                {
                    "status": r.status.value,
                    "modules": r.reloaded_modules,
                    "timestamp": r.timestamp.isoformat(),
                    "error": r.error_message,
                }
                for r in history
            ]

        return status

    def get_reload_history(self, limit: int = 10) -> list[ReloadResult]:
        """Get recent hot-reload history.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of recent ReloadResults.
        """
        if not self._hot_reloader:
            return []
        return self._hot_reloader.get_reload_history(limit)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id not in self._tasks:
            return False

        self._tasks[task_id].cancel()
        return True
