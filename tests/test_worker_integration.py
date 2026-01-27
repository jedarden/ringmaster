"""Integration tests for worker execution flow.

These tests verify the full execution path from task assignment to completion,
including output streaming, status updates, and metric recording.
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Priority, Project, Task, TaskStatus, Worker, WorkerStatus
from ringmaster.scheduler.manager import Scheduler
from ringmaster.worker.executor import WorkerExecutor, calculate_retry_backoff
from ringmaster.worker.interface import (
    SessionConfig,
    SessionHandle,
    SessionResult,
    SessionStatus,
    WorkerInterface,
)


class MockWorkerInterface(WorkerInterface):
    """Mock worker that simulates CLI tool behavior.

    Produces output lines with configurable delay to simulate
    real CLI execution behavior.
    """

    def __init__(
        self,
        name: str = "mock-worker",
        output_lines: list[str] | None = None,
        should_succeed: bool = True,
        delay_per_line: float = 0.01,
        include_completion_signal: bool = True,
    ):
        self._name = name
        self.output_lines = output_lines or [
            "Starting task...",
            "Processing...",
            "Making changes...",
        ]
        if include_completion_signal and should_succeed:
            self.output_lines.append("<promise>COMPLETE</promise>")
        self.should_succeed = should_succeed
        self.delay_per_line = delay_per_line
        self._sessions_started = 0
        self._last_config: SessionConfig | None = None

    @property
    def name(self) -> str:
        return self._name

    async def is_available(self) -> bool:
        return True

    async def start_session(self, config: SessionConfig) -> "MockSessionHandle":
        self._sessions_started += 1
        self._last_config = config
        return MockSessionHandle(
            config=config,
            worker_name=self._name,
            output_lines=self.output_lines,
            should_succeed=self.should_succeed,
            delay_per_line=self.delay_per_line,
        )


class MockSessionHandle:
    """Mock session handle that simulates streaming output."""

    def __init__(
        self,
        config: SessionConfig,
        worker_name: str,
        output_lines: list[str],
        should_succeed: bool = True,
        delay_per_line: float = 0.01,
    ):
        self.config = config
        self.worker_name = worker_name
        self.output_lines = output_lines
        self.should_succeed = should_succeed
        self.delay_per_line = delay_per_line
        self._streamed = False
        self._output: list[str] = []
        self._started_at = datetime.now(UTC)

    async def stream_output(self):
        """Stream output lines with simulated delay."""
        self._streamed = True
        for line in self.output_lines:
            await asyncio.sleep(self.delay_per_line)
            self._output.append(line)
            yield line

    async def wait(self) -> SessionResult:
        """Wait for completion and return result."""
        # Ensure streaming happened
        if not self._streamed:
            async for _ in self.stream_output():
                pass

        status = SessionStatus.COMPLETED if self.should_succeed else SessionStatus.FAILED
        return SessionResult(
            status=status,
            output="\n".join(self._output),
            exit_code=0 if self.should_succeed else 1,
            started_at=self._started_at,
            ended_at=datetime.now(UTC),
        )


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.disconnect()


@pytest.fixture
async def project(db):
    """Create a test project."""
    repo = ProjectRepository(db)
    project = Project(
        name="Test Integration Project",
        description="A project for integration testing",
        tech_stack=["python", "fastapi"],
    )
    return await repo.create(project)


@pytest.fixture
async def task(db, project):
    """Create a test task."""
    repo = TaskRepository(db)
    task = Task(
        project_id=project.id,
        title="Implement test feature",
        description="Add a new utility function for testing",
        priority=Priority.P1,
        status=TaskStatus.READY,
    )
    return await repo.create_task(task)


@pytest.fixture
async def worker(db):
    """Create a test worker."""
    repo = WorkerRepository(db)
    worker = Worker(
        name="Mock Worker",
        type="mock-worker",
        command="mock-cli",
        status=WorkerStatus.IDLE,
    )
    return await repo.create(worker)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create minimal project structure
        src_dir = project_dir / "src" / "myproject"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text('"""My project."""\n')
        (src_dir / "utils.py").write_text('"""Utility functions."""\n\ndef helper(): pass\n')

        yield project_dir


class TestWorkerExecution:
    """Tests for worker execution with mock interface."""

    @pytest.mark.asyncio
    async def test_execute_task_success_flow(self, db, project, task, worker, temp_project_dir):
        """Test successful task execution flow."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(should_succeed=True)

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                result = await executor.execute_task(task, worker)

            # Verify result
            assert result.success is True
            assert result.status == SessionStatus.COMPLETED
            assert "<promise>COMPLETE</promise>" in result.output

            # Verify mock was called
            assert mock_interface._sessions_started == 1
            assert mock_interface._last_config is not None
            assert "Implement test feature" in mock_interface._last_config.prompt

    @pytest.mark.asyncio
    async def test_execute_task_failure_flow(self, db, project, task, worker, temp_project_dir):
        """Test failed task execution flow."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(
                should_succeed=False,
                include_completion_signal=False,
                output_lines=["Error: Something went wrong", "Aborting..."],
            )

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                result = await executor.execute_task(task, worker)

            # Verify result
            assert result.success is False
            assert result.status == SessionStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_task_updates_status(self, db, project, task, worker, temp_project_dir):
        """Test that task status is updated during execution."""
        task_repo = TaskRepository(db)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            # Track status changes
            status_history = []

            original_update = task_repo.update_task

            async def tracking_update(t):
                status_history.append(t.status)
                return await original_update(t)

            task_repo.update_task = tracking_update
            executor.task_repo = task_repo

            mock_interface = MockWorkerInterface(should_succeed=True)

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Should have status updates including IN_PROGRESS and REVIEW
            assert TaskStatus.IN_PROGRESS in status_history
            assert TaskStatus.REVIEW in status_history

    @pytest.mark.asyncio
    async def test_execute_task_streams_output(self, db, project, task, worker, temp_project_dir):
        """Test that output is streamed during execution."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            streamed_lines = []

            def on_output(line: str):
                streamed_lines.append(line)

            mock_interface = MockWorkerInterface(
                output_lines=["Line 1", "Line 2", "Line 3"],
                should_succeed=True,
                include_completion_signal=False,  # Don't auto-add completion signal
            )

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker, on_output=on_output)

            # Verify all lines were streamed
            assert len(streamed_lines) == 3
            assert "Line 1" in streamed_lines
            assert "Line 3" in streamed_lines

    @pytest.mark.asyncio
    async def test_execute_task_records_metrics(self, db, project, task, worker, temp_project_dir):
        """Test that execution metrics are recorded."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(should_succeed=True)

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Check metrics were recorded
            result = await db.fetchone(
                "SELECT * FROM session_metrics WHERE task_id = ?",
                (task.id,),
            )
            assert result is not None
            assert result["worker_id"] == worker.id
            assert result["success"] == 1  # SQLite stores True as 1

    @pytest.mark.asyncio
    async def test_execute_task_updates_worker_status(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that worker status is updated during execution."""
        worker_repo = WorkerRepository(db)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(should_succeed=True)

            # Worker starts IDLE
            assert worker.status == WorkerStatus.IDLE

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Refresh worker from DB
            updated_worker = await worker_repo.get(worker.id)

            # Worker should be IDLE after completion
            assert updated_worker.status == WorkerStatus.IDLE
            assert updated_worker.tasks_completed == 1
            assert updated_worker.current_task_id is None

    @pytest.mark.asyncio
    async def test_execute_task_saves_output_file(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that task output is saved to file."""
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            executor = WorkerExecutor(
                db,
                output_dir=output_path,
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(
                output_lines=["Test output line 1", "Test output line 2"],
                should_succeed=True,
            )

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Check output file exists
            task_dir = output_path / task.id
            assert task_dir.exists()

            output_files = list(task_dir.glob("iteration_*.log"))
            assert len(output_files) >= 1

            content = output_files[0].read_text()
            assert "Test output line 1" in content

    @pytest.mark.asyncio
    async def test_execute_task_increments_attempts(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that task attempts counter is incremented."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            initial_attempts = task.attempts
            mock_interface = MockWorkerInterface(should_succeed=True)

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            assert task.attempts == initial_attempts + 1


class TestSchedulerIntegration:
    """Tests for scheduler integration with worker execution."""

    @pytest.mark.asyncio
    async def test_scheduler_status_includes_active_tasks(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that scheduler status includes active task information."""
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            project_root=temp_project_dir,
            enable_hot_reload=False,
        )

        # Get status before starting
        status = await scheduler.get_status()
        assert status["running"] is False
        assert status["active_task_count"] == 0
        assert "queue_stats" in status

    @pytest.mark.asyncio
    async def test_scheduler_start_stop_lifecycle(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test scheduler start/stop lifecycle."""
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            project_root=temp_project_dir,
            enable_hot_reload=False,
        )

        # Start scheduler
        await scheduler.start()
        assert scheduler._running is True

        # Stop scheduler
        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_scheduler_executes_with_mock_worker(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that scheduler can execute tasks with mocked worker."""
        with tempfile.TemporaryDirectory() as output_dir:
            scheduler = Scheduler(
                db,
                poll_interval=0.1,
                project_root=temp_project_dir,
                output_dir=Path(output_dir),
                enable_hot_reload=False,
            )

            mock_interface = MockWorkerInterface(
                should_succeed=True,
                delay_per_line=0.001,
            )

            # Manually trigger task execution to avoid timing issues
            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await scheduler._start_task_execution(task, worker)

                # Wait for the internal task to complete
                if task.id in scheduler._tasks:
                    await scheduler._tasks[task.id]

            # Verify mock was called
            assert mock_interface._sessions_started == 1


class TestWorkerUnavailable:
    """Tests for handling unavailable workers."""

    @pytest.mark.asyncio
    async def test_execute_fails_when_worker_unavailable(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test execution fails gracefully when worker CLI not found."""

        class UnavailableWorker(WorkerInterface):
            @property
            def name(self) -> str:
                return "unavailable"

            async def is_available(self) -> bool:
                return False

            async def start_session(self, config: SessionConfig) -> SessionHandle:
                raise RuntimeError("Should not be called")

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            with patch("ringmaster.worker.executor.get_worker", return_value=UnavailableWorker()):
                result = await executor.execute_task(task, worker)

            assert result.success is False
            assert "not found" in result.error.lower() or "not available" in result.error.lower()


class TestEnrichmentIntegration:
    """Tests for enrichment pipeline integration during execution."""

    @pytest.mark.asyncio
    async def test_enriched_prompt_contains_task_context(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that enriched prompt includes task information."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(should_succeed=True)
            captured_config = None

            # Capture the config passed to mock interface
            original_start = mock_interface.start_session

            async def capturing_start(config):
                nonlocal captured_config
                captured_config = config
                return await original_start(config)

            mock_interface.start_session = capturing_start

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Verify prompt contains task info
            assert captured_config is not None
            assert task.title in captured_config.prompt
            assert "COMPLETE" in captured_config.prompt

    @pytest.mark.asyncio
    async def test_enriched_prompt_contains_project_context(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that enriched prompt includes project information."""
        # Update project with more details
        project.tech_stack = ["python", "pytest", "asyncio"]
        await ProjectRepository(db).update(project)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(should_succeed=True)

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Verify prompt contains project info
            prompt = mock_interface._last_config.prompt
            assert project.name in prompt


class TestRetryBackoffCalculation:
    """Tests for the exponential backoff calculation function."""

    def test_backoff_increases_exponentially(self):
        """Test that backoff increases exponentially with attempts."""
        delay_1 = calculate_retry_backoff(1)
        delay_2 = calculate_retry_backoff(2)
        delay_3 = calculate_retry_backoff(3)
        delay_4 = calculate_retry_backoff(4)

        # Default base is 30s, so:
        # attempt 1: 30s, attempt 2: 60s, attempt 3: 120s, attempt 4: 240s
        assert delay_1.total_seconds() == 30
        assert delay_2.total_seconds() == 60
        assert delay_3.total_seconds() == 120
        assert delay_4.total_seconds() == 240

    def test_backoff_caps_at_max(self):
        """Test that backoff is capped at max_delay."""
        # With default max of 3600s, attempt 8 would be 30*128=3840s, capped to 3600
        delay = calculate_retry_backoff(8)
        assert delay.total_seconds() == 3600

    def test_custom_base_delay(self):
        """Test custom base delay configuration."""
        delay = calculate_retry_backoff(1, base_delay_seconds=60)
        assert delay.total_seconds() == 60

        delay_2 = calculate_retry_backoff(2, base_delay_seconds=60)
        assert delay_2.total_seconds() == 120

    def test_custom_max_delay(self):
        """Test custom max delay cap."""
        delay = calculate_retry_backoff(5, base_delay_seconds=30, max_delay_seconds=100)
        # 30 * 2^4 = 480, capped to 100
        assert delay.total_seconds() == 100

    def test_zero_attempts_uses_base(self):
        """Test that zero or negative attempts use base delay."""
        delay = calculate_retry_backoff(0)
        assert delay.total_seconds() == 30


class TestRetryBackoff:
    """Tests for task retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_failed_task_gets_retry_after_set(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that failed tasks have retry_after set for backoff."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            # Mock worker that fails
            mock_interface = MockWorkerInterface(
                should_succeed=False,
                include_completion_signal=False,
                output_lines=["Starting...", "Error: Something went wrong"],
            )

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Reload task from database
            task_repo = TaskRepository(db)
            updated_task = await task_repo.get_task(task.id)

            # Task should be ready for retry with retry_after set
            assert updated_task.status == TaskStatus.READY
            assert updated_task.retry_after is not None
            assert updated_task.retry_after > datetime.now(UTC)
            assert updated_task.last_failure_reason is not None

    @pytest.mark.asyncio
    async def test_retry_after_increases_with_attempts(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that retry backoff increases with each attempt."""
        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(
                should_succeed=False,
                include_completion_signal=False,
            )

            # First failure
            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            task_repo = TaskRepository(db)
            task_after_first = await task_repo.get_task(task.id)
            first_retry_delay = (task_after_first.retry_after - datetime.now(UTC)).total_seconds()

            # Reset task status and clear retry_after for next attempt
            task_after_first.status = TaskStatus.READY
            task_after_first.retry_after = None
            await task_repo.update_task(task_after_first)

            # Reset worker status
            worker_repo = WorkerRepository(db)
            worker.status = WorkerStatus.IDLE
            worker.current_task_id = None
            await worker_repo.update(worker)

            # Second failure (attempts=2 after this)
            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task_after_first, worker)

            task_after_second = await task_repo.get_task(task.id)
            second_retry_delay = (task_after_second.retry_after - datetime.now(UTC)).total_seconds()

            # Second backoff should be longer than first
            # Base is 30s, so first=30s, second=60s (approximately)
            assert second_retry_delay > first_retry_delay

    @pytest.mark.asyncio
    async def test_success_clears_retry_tracking(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that successful task clears retry tracking fields."""
        # Set up task with retry tracking from previous failure
        task.attempts = 2
        task.retry_after = datetime.now(UTC)
        task.last_failure_reason = "Previous failure"
        task_repo = TaskRepository(db)
        await task_repo.update_task(task)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(should_succeed=True)

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Reload task
            updated_task = await task_repo.get_task(task.id)

            # Retry tracking should be cleared
            assert updated_task.retry_after is None
            assert updated_task.last_failure_reason is None

    @pytest.mark.asyncio
    async def test_max_attempts_reached_no_retry(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that task is marked FAILED when max attempts reached."""
        # Set task close to max attempts
        task.attempts = task.max_attempts - 1
        task_repo = TaskRepository(db)
        await task_repo.update_task(task)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                db,
                output_dir=Path(output_dir),
                project_dir=temp_project_dir,
            )

            mock_interface = MockWorkerInterface(
                should_succeed=False,
                include_completion_signal=False,
            )

            with patch("ringmaster.worker.executor.get_worker", return_value=mock_interface):
                await executor.execute_task(task, worker)

            # Reload task
            updated_task = await task_repo.get_task(task.id)

            # Task should be failed, not ready for retry
            assert updated_task.status == TaskStatus.FAILED
            assert updated_task.retry_after is None

    @pytest.mark.asyncio
    async def test_get_ready_tasks_filters_pending_retries(
        self, db, project, task, temp_project_dir
    ):
        """Test that get_ready_tasks filters out tasks with future retry_after."""
        task_repo = TaskRepository(db)

        # Create a task with retry_after in the future
        from datetime import timedelta
        task.status = TaskStatus.READY
        task.retry_after = datetime.now(UTC) + timedelta(minutes=5)
        await task_repo.update_task(task)

        # Create another task that's ready immediately
        from uuid import uuid4

        from ringmaster.domain import Task as TaskModel
        ready_task = TaskModel(
            id=f"bd-{uuid4().hex[:8]}",
            project_id=project.id,
            title="Ready task",
            status=TaskStatus.READY,
            retry_after=None,
        )
        await task_repo.create_task(ready_task)

        # Get ready tasks
        ready_tasks = await task_repo.get_ready_tasks()

        # Should only include the immediately ready task
        task_ids = [t.id for t in ready_tasks]
        assert ready_task.id in task_ids
        assert task.id not in task_ids  # Still in backoff period
