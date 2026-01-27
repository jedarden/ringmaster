"""Worker executor for running coding tasks."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ringmaster.db import Database, ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.db.repositories import ReasoningBankRepository
from ringmaster.domain import Project, Task, TaskOutcome, TaskStatus, Worker, WorkerStatus
from ringmaster.enricher import EnrichmentPipeline
from ringmaster.events import EventBus, EventType
from ringmaster.git import (
    GitError,
    WorktreeConfig,
    get_or_create_worktree,
    get_worktree_status,
    is_git_repo,
)
from ringmaster.queue.routing import extract_keywords, generate_success_reflection
from ringmaster.worker.interface import SessionConfig, SessionResult, SessionStatus
from ringmaster.worker.monitor import (
    RecoveryAction,
    WorkerMonitor,
    recommend_recovery,
)
from ringmaster.worker.outcome import Outcome, OutcomeResult, detect_outcome
from ringmaster.worker.output_buffer import output_buffer
from ringmaster.worker.platforms import get_worker

logger = logging.getLogger(__name__)


def calculate_retry_backoff(attempts: int, base_delay_seconds: int = 30, max_delay_seconds: int = 3600) -> timedelta:
    """Calculate exponential backoff delay for task retry.

    Uses exponential backoff with a cap: delay = base * 2^(attempts-1)
    - Attempt 1: 30s
    - Attempt 2: 60s
    - Attempt 3: 120s
    - Attempt 4: 240s
    - Attempt 5: 480s (capped at max_delay)

    Args:
        attempts: Current number of attempts (1-based)
        base_delay_seconds: Base delay in seconds (default 30)
        max_delay_seconds: Maximum delay cap in seconds (default 3600 = 1 hour)

    Returns:
        Timedelta representing the backoff delay
    """
    # Exponential backoff: base * 2^(attempts-1)
    exponent = max(0, attempts - 1)
    delay_seconds = min(base_delay_seconds * (2 ** exponent), max_delay_seconds)
    return timedelta(seconds=delay_seconds)


class WorkerExecutor:
    """Executes coding tasks using worker interfaces.

    Responsibilities:
    - Start worker sessions for assigned tasks
    - Monitor session progress
    - Handle completion and failure
    - Record metrics
    - Enrich prompts with project/code/history context
    - Isolate workers using git worktrees for parallel execution
    """

    def __init__(
        self,
        db: Database,
        output_dir: Path | None = None,
        project_dir: Path | None = None,
        event_bus: EventBus | None = None,
        use_worktrees: bool = True,
    ):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.worker_repo = WorkerRepository(db)
        self.project_repo = ProjectRepository(db)
        self.reasoning_bank = ReasoningBankRepository(db)
        self.output_dir = output_dir or Path.home() / ".ringmaster" / "tasks"
        self.project_dir = project_dir or Path.cwd()
        self.event_bus = event_bus
        self.use_worktrees = use_worktrees
        self._active_sessions: dict[str, asyncio.Task] = {}
        self._enrichment_pipeline: EnrichmentPipeline | None = None
        self._monitors: dict[str, WorkerMonitor] = {}  # worker_id -> monitor
        self._monitor_check_interval: float = 30.0  # seconds between monitor checks

    @property
    def enrichment_pipeline(self) -> EnrichmentPipeline:
        """Get or create the enrichment pipeline (lazy initialization)."""
        if self._enrichment_pipeline is None:
            self._enrichment_pipeline = EnrichmentPipeline(
                project_dir=self.project_dir,
                db=self.db,
            )
        return self._enrichment_pipeline

    async def _get_working_directory(
        self,
        task: Task,
        worker: Worker,
        project: Project,
    ) -> Path:
        """Determine the working directory for task execution.

        Uses git worktrees for worker isolation when:
        1. use_worktrees is enabled
        2. Project has a valid repo_url pointing to a git repository

        Each worker gets a dedicated worktree so multiple workers can
        execute tasks in parallel without file conflicts.

        Args:
            task: The task being executed.
            worker: The worker executing the task.
            project: The project containing the task.

        Returns:
            Path to the working directory for task execution.
        """
        # Determine base project directory
        if project.repo_url and Path(project.repo_url).is_dir():
            project_dir = Path(project.repo_url)
        elif worker.working_dir:
            project_dir = Path(worker.working_dir)
        else:
            project_dir = Path.cwd()

        # Check if we should use worktrees
        if not self.use_worktrees:
            return project_dir

        # Check if the project directory is a git repo
        is_repo = await is_git_repo(project_dir)
        if not is_repo:
            logger.debug(
                f"Project {project.id} at {project_dir} is not a git repo, "
                "skipping worktree"
            )
            return project_dir

        # Get or create worktree for this worker
        try:
            config = WorktreeConfig(
                worker_id=worker.id,
                task_id=task.id,
            )

            # Use project setting for base branch, default to "main"
            base_branch = project.settings.get("base_branch", "main")

            worktree = await get_or_create_worktree(
                repo_path=project_dir,
                config=config,
                base_branch=base_branch,
            )

            logger.info(
                f"Using worktree at {worktree.path} (branch: {worktree.branch}) "
                f"for worker {worker.id} task {task.id}"
            )
            return worktree.path

        except GitError as e:
            logger.warning(
                f"Failed to create worktree for worker {worker.id}: {e}, "
                "falling back to project directory"
            )
            return project_dir

    async def _report_worktree_status(
        self,
        task: Task,
        worker: Worker,
        project_dir: Path,
    ) -> dict | None:
        """Get and log worktree status after task execution.

        Args:
            task: The completed task.
            worker: The worker that executed the task.
            project_dir: The project's base directory.

        Returns:
            Worktree status dict, or None if not using worktrees.
        """
        if not self.use_worktrees:
            return None

        try:
            status = await get_worktree_status(project_dir, worker.id)
            if status.get("exists"):
                logger.info(
                    f"Worktree status for worker {worker.id}: "
                    f"branch={status.get('branch')}, "
                    f"changes={status.get('has_uncommitted_changes')}, "
                    f"commits_ahead={status.get('commits_ahead')}"
                )
                return status
        except GitError as e:
            logger.warning(f"Failed to get worktree status: {e}")

        return None

    def _get_monitor(self, worker_id: str, task_id: str | None = None) -> WorkerMonitor:
        """Get or create a monitor for a worker.

        Args:
            worker_id: The worker ID to monitor.
            task_id: The task being executed.

        Returns:
            WorkerMonitor instance.
        """
        if worker_id not in self._monitors:
            self._monitors[worker_id] = WorkerMonitor(worker_id=worker_id, task_id=task_id)
        else:
            # Reset for new task
            self._monitors[worker_id].reset(task_id=task_id)
        return self._monitors[worker_id]

    async def _handle_recovery(
        self,
        recovery: RecoveryAction,
        task: Task,
        worker: Worker,
    ) -> bool:
        """Handle a recommended recovery action.

        Args:
            recovery: The recommended action.
            task: The task being executed.
            worker: The worker executing the task.

        Returns:
            True if execution should be interrupted, False otherwise.
        """
        if recovery.action == "none":
            return False

        if recovery.action == "log_warning":
            logger.warning(
                f"Worker {worker.id} task {task.id}: {recovery.reason}"
            )
            return False

        if recovery.action == "interrupt":
            logger.warning(
                f"Worker {worker.id} task {task.id} needs interrupt: {recovery.reason}"
            )
            # Emit event for UI notification
            if self.event_bus:
                await self.event_bus.emit(
                    EventType.WORKER_STATUS,
                    {
                        "worker_id": worker.id,
                        "task_id": task.id,
                        "status": "hung",
                        "reason": recovery.reason,
                        "action": recovery.action,
                    },
                    project_id=task.project_id,
                )
            return True  # Signal to interrupt execution

        if recovery.action == "checkpoint_restart":
            logger.warning(
                f"Worker {worker.id} task {task.id} needs restart: {recovery.reason}"
            )
            # Emit event for UI notification
            if self.event_bus:
                await self.event_bus.emit(
                    EventType.WORKER_STATUS,
                    {
                        "worker_id": worker.id,
                        "task_id": task.id,
                        "status": "degraded",
                        "reason": recovery.reason,
                        "action": recovery.action,
                    },
                    project_id=task.project_id,
                )
            return True  # Signal to interrupt and restart with fresh context

        if recovery.action == "escalate":
            logger.error(
                f"Worker {worker.id} task {task.id} needs escalation: {recovery.reason}"
            )
            if self.event_bus:
                await self.event_bus.emit(
                    EventType.WORKER_STATUS,
                    {
                        "worker_id": worker.id,
                        "task_id": task.id,
                        "status": "escalate",
                        "reason": recovery.reason,
                        "action": recovery.action,
                    },
                    project_id=task.project_id,
                )
            return True

        return False

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

        # Prepare working directory - use worktree for worker isolation if available
        working_dir = await self._get_working_directory(task, worker, project)

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

        # Initialize monitor for this execution
        monitor = self._get_monitor(worker.id, task.id)
        should_interrupt = False
        last_monitor_check = datetime.now(UTC)

        try:
            # Clear previous output in buffer
            await output_buffer.clear(worker.id)

            # Stream output to file, buffer, callback, and monitor
            output_file = task_output_dir / f"iteration_{task.attempts:03d}.log"
            with open(output_file, "w") as f:
                async for line in handle.stream_output():
                    f.write(line + "\n")
                    f.flush()

                    # Write to output buffer for streaming
                    await output_buffer.write(worker.id, line)

                    # Record output in monitor for liveness/degradation tracking
                    await monitor.record_output(line)

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

                    # Periodic monitoring check (every N seconds)
                    now = datetime.now(UTC)
                    if (now - last_monitor_check).total_seconds() >= self._monitor_check_interval:
                        last_monitor_check = now
                        recovery = recommend_recovery(monitor)
                        should_interrupt = await self._handle_recovery(recovery, task, worker)
                        if should_interrupt:
                            logger.warning(
                                f"Interrupting task {task.id} due to {recovery.action}: "
                                f"{recovery.reason}"
                            )
                            break

            # Wait for completion (unless interrupted)
            if not should_interrupt:
                result = await handle.wait()
            else:
                # Force stop the session if interrupted
                await handle.stop()
                result = SessionResult(
                    status=SessionStatus.TIMEOUT,
                    output="",
                    error=f"Interrupted: {recovery.reason}",  # type: ignore
                )

            # Determine outcome using multi-signal detection
            outcome_result = detect_outcome(
                output=result.output,
                exit_code=result.exit_code,
            )

            logger.info(
                f"Task {task.id} outcome: {outcome_result.outcome.value} "
                f"(confidence: {outcome_result.confidence:.2f}, reason: {outcome_result.reason})"
            )

            # Update task based on detected outcome
            task.output_path = str(output_file)

            if outcome_result.outcome == Outcome.NEEDS_DECISION:
                # Worker needs human input - block the task
                task.status = TaskStatus.BLOCKED
                task.blocked_reason = outcome_result.decision_question or outcome_result.reason
                # Emit event for UI notification
                if self.event_bus:
                    await self.event_bus.emit(
                        EventType.TASK_STATUS,
                        {
                            "task_id": task.id,
                            "status": task.status.value,
                            "outcome": outcome_result.outcome.value,
                            "decision_question": outcome_result.decision_question,
                            "needs_human_input": True,
                        },
                        project_id=task.project_id,
                    )
            elif outcome_result.is_success:
                task.status = TaskStatus.REVIEW  # Go to review before done
                task.completed_at = datetime.now(UTC)
                # Clear retry tracking on success
                task.retry_after = None
                task.last_failure_reason = None
            else:
                # Failure - record reason and schedule retry with backoff
                task.last_failure_reason = outcome_result.reason or result.error or "Unknown failure"

                if task.attempts >= task.max_attempts:
                    task.status = TaskStatus.FAILED
                    task.retry_after = None  # No more retries
                else:
                    # Schedule retry with exponential backoff
                    task.status = TaskStatus.READY
                    backoff = calculate_retry_backoff(task.attempts)
                    task.retry_after = datetime.now(UTC) + backoff

                    logger.info(
                        f"Task {task.id} scheduled for retry in {backoff.total_seconds():.0f}s "
                        f"(attempt {task.attempts}/{task.max_attempts})"
                    )

                    # Emit retry event
                    if self.event_bus:
                        await self.event_bus.emit(
                            EventType.TASK_RETRY,
                            {
                                "task_id": task.id,
                                "attempts": task.attempts,
                                "max_attempts": task.max_attempts,
                                "retry_after": task.retry_after.isoformat(),
                                "backoff_seconds": backoff.total_seconds(),
                                "failure_reason": task.last_failure_reason,
                            },
                            project_id=task.project_id,
                        )

            await self.task_repo.update_task(task)

            # Update worker
            if outcome_result.is_success:
                worker.tasks_completed += 1
            elif outcome_result.is_failure:
                worker.tasks_failed += 1
            # NEEDS_DECISION doesn't count as completed or failed
            worker.status = WorkerStatus.IDLE
            worker.current_task_id = None
            worker.last_active_at = datetime.now(UTC)
            await self.worker_repo.update(worker)

            # Record metrics
            await self._record_metrics(task, worker, result, outcome_result)

            # Report worktree status (for debugging/auditing)
            if project.repo_url and Path(project.repo_url).is_dir():
                await self._report_worktree_status(task, worker, Path(project.repo_url))

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
        outcome_result: "OutcomeResult | None" = None,
    ) -> None:
        """Record session metrics to the database."""
        # Use outcome parser result if available
        success = outcome_result.is_success if outcome_result else result.success
        outcome_value = outcome_result.outcome.value if outcome_result else None
        outcome_confidence = outcome_result.confidence if outcome_result else None

        await self.db.execute(
            """
            INSERT INTO session_metrics (
                task_id, worker_id, iteration, input_tokens, output_tokens,
                estimated_cost_usd, started_at, ended_at, duration_seconds,
                success, error_message, outcome, outcome_confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                success,
                result.error,
                outcome_value,
                outcome_confidence,
            ),
        )
        await self.db.commit()

        # Record outcome to reasoning bank for reflexion-based learning
        if outcome_result:
            await self._record_outcome(task, worker, result, outcome_result)

    async def _record_outcome(
        self,
        task: Task,
        worker: Worker,
        result: SessionResult,
        outcome_result: OutcomeResult,
    ) -> None:
        """Record task outcome to the reasoning bank for learning.

        Per docs/08-open-architecture.md "Reflexion-Based Learning" section:
        Store task execution results to enable model routing optimization
        based on learned experience.
        """
        # Check if the task has dependencies
        dependencies = await self.task_repo.get_dependencies(task.id)
        has_dependencies = len(dependencies) > 0

        # Extract keywords for similarity matching
        keywords = extract_keywords(task)

        # Estimate file count from task description
        from ringmaster.queue.routing import _count_suggested_files
        file_count = _count_suggested_files(task)

        # Generate reflection based on outcome
        if outcome_result.is_success:
            reflection = generate_success_reflection(
                task=task,
                model_used=worker.type,  # TODO: Track actual model used
                iterations=task.attempts,
                file_count=file_count,
            )
        else:
            # For failures, include the failure reason
            reflection = (
                f"Failed on {task.type.value if hasattr(task.type, 'value') else task.type} task. "
                f"Reason: {outcome_result.reason or 'Unknown'}. "
                f"Model {worker.type} attempted {task.attempts} iterations."
            )

        outcome = TaskOutcome(
            task_id=task.id,
            project_id=task.project_id,
            file_count=file_count,
            keywords=keywords,
            bead_type=task.type.value if hasattr(task.type, "value") else str(task.type),
            has_dependencies=has_dependencies,
            model_used=worker.type,  # TODO: Track actual model used (e.g., claude-sonnet-4)
            worker_type=worker.type,
            iterations=task.attempts,
            duration_seconds=int(result.duration_seconds or 0),
            success=outcome_result.is_success,
            outcome=outcome_result.outcome.value,
            confidence=outcome_result.confidence,
            failure_reason=outcome_result.reason if not outcome_result.is_success else None,
            reflection=reflection,
        )

        try:
            await self.reasoning_bank.record(outcome)
            logger.debug(
                f"Recorded outcome for task {task.id}: "
                f"{outcome_result.outcome.value} (confidence: {outcome_result.confidence:.2f})"
            )
        except Exception as e:
            # Don't fail the task execution if outcome recording fails
            logger.warning(f"Failed to record outcome for task {task.id}: {e}")

    @property
    def active_tasks(self) -> list[str]:
        """Get list of currently executing task IDs."""
        return list(self._active_sessions.keys())
