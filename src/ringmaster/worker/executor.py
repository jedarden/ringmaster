"""Worker executor for running coding tasks."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ringmaster.db import Database, TaskRepository, WorkerRepository
from ringmaster.domain import Task, TaskStatus, Worker, WorkerStatus
from ringmaster.worker.interface import SessionConfig, SessionResult, SessionStatus
from ringmaster.worker.platforms import get_worker

logger = logging.getLogger(__name__)


class WorkerExecutor:
    """Executes coding tasks using worker interfaces.

    Responsibilities:
    - Start worker sessions for assigned tasks
    - Monitor session progress
    - Handle completion and failure
    - Record metrics
    """

    def __init__(self, db: Database, output_dir: Path | None = None):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.worker_repo = WorkerRepository(db)
        self.output_dir = output_dir or Path.home() / ".ringmaster" / "tasks"
        self._active_sessions: dict[str, asyncio.Task] = {}

    async def execute_task(
        self,
        task: Task,
        worker: Worker,
        on_output: Callable[[str], None] | None = None,
    ) -> SessionResult:
        """Execute a task using the specified worker.

        Args:
            task: The task to execute.
            worker: The worker configuration to use.
            on_output: Optional callback for streaming output.

        Returns:
            SessionResult with outcome details.
        """
        logger.info(f"Executing task {task.id} with worker {worker.id}")

        # Update task status
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(UTC)
        task.attempts += 1
        await self.task_repo.update_task(task)

        # Update worker status
        worker.status = WorkerStatus.BUSY
        worker.current_task_id = task.id
        worker.last_active_at = datetime.now(UTC)
        await self.worker_repo.update(worker)

        # Create output directory for this task
        task_output_dir = self.output_dir / task.id
        task_output_dir.mkdir(parents=True, exist_ok=True)

        # Prepare working directory
        working_dir = Path(worker.working_dir) if worker.working_dir else Path.cwd()

        # Build the prompt
        prompt = self._build_prompt(task)

        # Create session config
        config = SessionConfig(
            working_dir=working_dir,
            prompt=prompt,
            timeout_seconds=worker.timeout_seconds,
            env_vars=worker.env_vars,
        )

        # Get worker interface
        worker_interface = get_worker(worker.type)

        # Check availability
        available = await worker_interface.is_available()
        if not available:
            logger.error(f"Worker {worker.type} is not available")
            return SessionResult(
                status=SessionStatus.FAILED,
                output="",
                error=f"Worker {worker.type} CLI not found",
            )

        # Start session
        handle = await worker_interface.start_session(config)

        # Store in active sessions
        self._active_sessions[task.id] = asyncio.current_task()  # type: ignore

        try:
            # Stream output to file and callback
            output_file = task_output_dir / f"iteration_{task.attempts:03d}.log"
            with open(output_file, "w") as f:
                async for line in handle.stream_output():
                    f.write(line + "\n")
                    f.flush()
                    if on_output:
                        on_output(line)

            # Wait for completion
            result = await handle.wait()

            # Update task
            task.output_path = str(output_file)
            if result.success:
                task.status = TaskStatus.REVIEW  # Go to review before done
                task.completed_at = datetime.now(UTC)
            else:
                if task.attempts >= task.max_attempts:
                    task.status = TaskStatus.FAILED
                else:
                    task.status = TaskStatus.READY  # Retry

            await self.task_repo.update_task(task)

            # Update worker
            if result.success:
                worker.tasks_completed += 1
            else:
                worker.tasks_failed += 1
            worker.status = WorkerStatus.IDLE
            worker.current_task_id = None
            worker.last_active_at = datetime.now(UTC)
            await self.worker_repo.update(worker)

            # Record metrics
            await self._record_metrics(task, worker, result)

            return result

        finally:
            # Cleanup
            self._active_sessions.pop(task.id, None)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel an active task execution.

        Returns True if cancelled, False if not found.
        """
        if task_id not in self._active_sessions:
            return False

        session_task = self._active_sessions[task_id]
        session_task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await session_task

        return True

    def _build_prompt(self, task: Task) -> str:
        """Build the prompt to send to the worker.

        TODO: Integrate with Enricher service for full context assembly.
        """
        parts = [
            f"# Task: {task.title}",
            "",
            task.description or "No description provided.",
            "",
            "## Instructions",
            "1. Implement the requested changes",
            "2. Ensure all tests pass",
            "3. Follow the project's coding conventions",
            "",
            f"When complete, output: {task.context_hash or '<promise>COMPLETE</promise>'}",
        ]
        return "\n".join(parts)

    async def _record_metrics(
        self,
        task: Task,
        worker: Worker,
        result: SessionResult,
    ) -> None:
        """Record session metrics to the database."""
        await self.db.execute(
            """
            INSERT INTO session_metrics (
                task_id, worker_id, iteration, input_tokens, output_tokens,
                estimated_cost_usd, started_at, ended_at, duration_seconds,
                success, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                worker.id,
                task.attempts,
                result.tokens_used,
                0,  # Output tokens not tracked yet
                result.cost_usd,
                result.started_at.isoformat() if result.started_at else None,
                result.ended_at.isoformat() if result.ended_at else None,
                result.duration_seconds,
                result.success,
                result.error,
            ),
        )
        await self.db.commit()

    @property
    def active_tasks(self) -> list[str]:
        """Get list of currently executing task IDs."""
        return list(self._active_sessions.keys())
