"""Worker executor for running coding tasks."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ringmaster.db import Database, ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Project, Task, TaskStatus, Worker, WorkerStatus
from ringmaster.enricher import EnrichmentPipeline
from ringmaster.events import EventBus, EventType
from ringmaster.worker.interface import SessionConfig, SessionResult, SessionStatus
from ringmaster.worker.output_buffer import output_buffer
from ringmaster.worker.platforms import get_worker

logger = logging.getLogger(__name__)


class WorkerExecutor:
    """Executes coding tasks using worker interfaces.

    Responsibilities:
    - Start worker sessions for assigned tasks
    - Monitor session progress
    - Handle completion and failure
    - Record metrics
    - Enrich prompts with project/code/history context
    """

    def __init__(
        self,
        db: Database,
        output_dir: Path | None = None,
        project_dir: Path | None = None,
        event_bus: EventBus | None = None,
    ):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.worker_repo = WorkerRepository(db)
        self.project_repo = ProjectRepository(db)
        self.output_dir = output_dir or Path.home() / ".ringmaster" / "tasks"
        self.project_dir = project_dir or Path.cwd()
        self.event_bus = event_bus
        self._active_sessions: dict[str, asyncio.Task] = {}
        self._enrichment_pipeline: EnrichmentPipeline | None = None

    @property
    def enrichment_pipeline(self) -> EnrichmentPipeline:
        """Get or create the enrichment pipeline (lazy initialization)."""
        if self._enrichment_pipeline is None:
            self._enrichment_pipeline = EnrichmentPipeline(
                project_dir=self.project_dir,
                db=self.db,
            )
        return self._enrichment_pipeline

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

        # Fetch project for context enrichment
        project = await self.project_repo.get(task.project_id)
        if not project:
            logger.error(f"Project {task.project_id} not found for task {task.id}")
            return SessionResult(
                status=SessionStatus.FAILED,
                output="",
                error=f"Project {task.project_id} not found",
            )

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

        # Prepare working directory - use project repo_url if set, else worker dir
        if project.repo_url and Path(project.repo_url).is_dir():
            working_dir = Path(project.repo_url)
        elif worker.working_dir:
            working_dir = Path(worker.working_dir)
        else:
            working_dir = Path.cwd()

        # Build the enriched prompt with context
        prompt = await self._build_enriched_prompt(task, project, task_output_dir)

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
            # Clear previous output in buffer
            await output_buffer.clear(worker.id)

            # Stream output to file, buffer, and callback
            output_file = task_output_dir / f"iteration_{task.attempts:03d}.log"
            with open(output_file, "w") as f:
                async for line in handle.stream_output():
                    f.write(line + "\n")
                    f.flush()

                    # Write to output buffer for streaming
                    await output_buffer.write(worker.id, line)

                    # Emit output event for real-time WebSocket updates
                    if self.event_bus:
                        await self.event_bus.emit(
                            EventType.WORKER_OUTPUT,
                            {
                                "worker_id": worker.id,
                                "task_id": task.id,
                                "line": line,
                            },
                            project_id=task.project_id,
                        )

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

    async def _build_enriched_prompt(
        self, task: Task, project: Project, output_dir: Path
    ) -> str:
        """Build an enriched prompt using the EnrichmentPipeline.

        The pipeline assembles context in layers:
        1. Task Context - Task title, description, state, iteration
        2. Project Context - Repo URL, tech stack, conventions
        3. Code Context - Relevant files based on task description
        4. History Context - RLM-summarized conversation history
        5. Refinement Context - Safety guardrails, constraints

        Args:
            task: The task to build a prompt for.
            project: The project the task belongs to.
            output_dir: Directory to save the assembled prompt.

        Returns:
            The assembled prompt string.
        """
        try:
            # Use enrichment pipeline for full context assembly
            assembled = await self.enrichment_pipeline.enrich(task, project)

            # Update task with context hash for tracking
            task.context_hash = assembled.context_hash
            await self.task_repo.update_task(task)

            # Save assembled prompt for debugging/auditing
            prompt_file = output_dir / f"prompt_{task.attempts:03d}.md"
            with open(prompt_file, "w") as f:
                f.write(f"# System Prompt\n\n{assembled.system_prompt}\n\n")
                f.write(f"# User Prompt\n\n{assembled.user_prompt}\n")
            task.prompt_path = str(prompt_file)

            logger.info(
                f"Built enriched prompt for task {task.id}: "
                f"~{assembled.metrics.estimated_tokens} tokens, "
                f"stages: {assembled.metrics.stages_applied}"
            )

            # Return the combined prompt (system + user for CLI workers)
            return f"{assembled.system_prompt}\n\n{assembled.user_prompt}"

        except Exception as e:
            # Fallback to basic prompt on enrichment failure
            logger.warning(f"Enrichment failed for task {task.id}, using fallback: {e}")
            return self._build_fallback_prompt(task)

    def _build_fallback_prompt(self, task: Task) -> str:
        """Build a basic prompt when enrichment fails.

        This is a safety fallback that provides minimal context.
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
            "When complete, output: <promise>COMPLETE</promise>",
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
