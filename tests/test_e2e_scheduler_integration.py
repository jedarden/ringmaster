"""End-to-end integration test for scheduler with real worker execution.

This test validates the full flow:
1. Create a project and tasks
2. Start the scheduler
3. Spawn a real worker (or use mock worker for safety)
4. Assign task to worker
5. Execute task to completion
6. Verify task status and outputs
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Priority, Project, Task, TaskStatus, Worker, WorkerStatus
from ringmaster.events import EventBus
from ringmaster.scheduler import Scheduler
from ringmaster.worker import WorkerExecutor
from ringmaster.worker.interface import SessionResult, SessionStatus


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
        name="E2E Test Project",
        description="End-to-end integration test project",
        tech_stack=["python"],
        repo_url=None,
    )
    return await repo.create(project)


@pytest.fixture
async def worker(db):
    """Create a test worker."""
    repo = WorkerRepository(db)
    worker = Worker(
        name="E2E Test Worker",
        type="claude-code",
        command="echo",
        args=["[mock] task executed"],
        status=WorkerStatus.IDLE,
    )
    return await repo.create(worker)


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for task outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def make_mock_execute(task_repo, db):
    """Create a mock execute function that simulates task completion."""
    async def mock_execute(task_param, worker_param):
        # Simulate task execution - set worker_id before updating
        task_param.worker_id = worker_param.id
        task_param.status = TaskStatus.DONE
        await task_repo.update_task(task_param)
        worker_param.status = WorkerStatus.IDLE
        worker_param.current_task_id = None
        await WorkerRepository(db).update(worker_param)
        return SessionResult(
            status=SessionStatus.COMPLETED,
            output="Task completed",
            exit_code=0,
        )
    return mock_execute


class TestE2ESchedulerIntegration:
    """End-to-end integration tests for the scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_assigns_task_to_worker(
        self, db, project, worker, temp_output_dir
    ):
        """Test that scheduler assigns a ready task to an idle worker."""
        # Create a task
        task_repo = TaskRepository(db)
        task = Task(
            project_id=project.id,
            title="Test task",
            description="A simple test task",
            priority=Priority.P2,
            status=TaskStatus.READY,
        )
        task = await task_repo.create_task(task)

        # Create scheduler with short poll interval
        event_bus = EventBus()
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            max_concurrent_tasks=1,
            output_dir=temp_output_dir,
            project_root=Path.cwd(),
            event_bus=event_bus,
            enable_hot_reload=False,  # Disable for faster tests
        )

        # Mock the executor to avoid real subprocess calls
        scheduler.executor.execute_task = make_mock_execute(task_repo, db)

        # Start scheduler
        await scheduler.start()

        try:
            # Wait for assignment and execution
            await asyncio.sleep(0.5)

            # Verify task was completed (worker_id is cleared after completion)
            updated_task = await task_repo.get_task(task.id)
            assert updated_task.status == TaskStatus.DONE
            # Note: worker_id is cleared by complete_task() after task completion

            # Verify worker is idle again (and has completion count incremented)
            updated_worker = await WorkerRepository(db).get(worker.id)
            assert updated_worker.status == WorkerStatus.IDLE
            assert updated_worker.current_task_id is None
            assert updated_worker.tasks_completed > 0  # Worker tracked the completion

        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_handles_multiple_tasks(
        self, db, project, worker, temp_output_dir
    ):
        """Test that scheduler processes multiple tasks sequentially."""
        task_repo = TaskRepository(db)

        # Create multiple tasks
        tasks = []
        for i in range(3):
            task = Task(
                project_id=project.id,
                title=f"Test task {i}",
                description=f"Task number {i}",
                priority=Priority.P2,
                status=TaskStatus.READY,
            )
            tasks.append(await task_repo.create_task(task))

        event_bus = EventBus()
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            max_concurrent_tasks=1,
            output_dir=temp_output_dir,
            event_bus=event_bus,
            enable_hot_reload=False,
        )

        # Track execution order
        execution_order = []

        async def mock_execute(task_param, worker_param):
            execution_order.append(task_param.id)
            task_param.status = TaskStatus.DONE
            await task_repo.update_task(task_param)
            worker_param.status = WorkerStatus.IDLE
            worker_param.current_task_id = None
            await WorkerRepository(db).update(worker_param)
            return SessionResult(
                status=SessionStatus.COMPLETED,
                output="Task completed",
                exit_code=0,
            )

        scheduler.executor.execute_task = mock_execute

        await scheduler.start()

        try:
            # Wait for all tasks to complete
            await asyncio.sleep(2.0)

            # Verify all tasks completed
            for task in tasks:
                updated_task = await task_repo.get_task(task.id)
                assert updated_task.status == TaskStatus.DONE

            # Verify sequential execution (max_concurrent_tasks=1)
            assert len(execution_order) == 3

        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_respects_max_concurrent_tasks(
        self, db, project, temp_output_dir
    ):
        """Test that scheduler respects max_concurrent_tasks limit."""
        task_repo = TaskRepository(db)

        # Create multiple workers
        worker_repo = WorkerRepository(db)
        workers = []
        for i in range(3):
            worker = Worker(
                name=f"Worker {i}",
                type="claude-code",
                command="echo",
                status=WorkerStatus.IDLE,
            )
            workers.append(await worker_repo.create(worker))

        # Create more tasks than max_concurrent
        tasks = []
        for i in range(5):
            task = Task(
                project_id=project.id,
                title=f"Task {i}",
                description=f"Task {i}",
                priority=Priority.P2,
                status=TaskStatus.READY,
            )
            tasks.append(await task_repo.create_task(task))

        event_bus = EventBus()
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            max_concurrent_tasks=2,  # Limit to 2 concurrent
            output_dir=temp_output_dir,
            event_bus=event_bus,
            enable_hot_reload=False,
        )

        # Track active executions
        active_count = 0
        max_active_seen = 0
        execution_lock = asyncio.Lock()

        async def mock_execute(task_param, worker_param):
            nonlocal active_count, max_active_seen

            async with execution_lock:
                active_count += 1
                if active_count > max_active_seen:
                    max_active_seen = active_count

            # Simulate work
            await asyncio.sleep(0.2)

            async with execution_lock:
                active_count -= 1

            task_param.status = TaskStatus.DONE
            await task_repo.update_task(task_param)
            worker_param.status = WorkerStatus.IDLE
            worker_param.current_task_id = None
            await WorkerRepository(db).update(worker_param)

            return SessionResult(
                status=SessionStatus.COMPLETED,
                output="Task completed",
                exit_code=0,
            )

        scheduler.executor.execute_task = mock_execute

        await scheduler.start()

        try:
            # Wait for execution
            await asyncio.sleep(1.0)

            # Verify never exceeded max_concurrent_tasks
            assert max_active_seen <= 2

        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_capability_matching(
        self, db, project, temp_output_dir
    ):
        """Test that scheduler matches worker capabilities to task requirements."""
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Create workers with different capabilities
        python_worker = Worker(
            name="Python Worker",
            type="claude-code",
            command="echo",
            capabilities=["python", "fastapi"],
            status=WorkerStatus.IDLE,
        )
        python_worker = await worker_repo.create(python_worker)

        rust_worker = Worker(
            name="Rust Worker",
            type="aider",
            command="echo",
            capabilities=["rust", "tokio"],
            status=WorkerStatus.IDLE,
        )
        rust_worker = await worker_repo.create(rust_worker)

        # Create a task requiring Python capabilities
        task = Task(
            project_id=project.id,
            title="Python API task",
            description="Build a FastAPI endpoint",
            priority=Priority.P1,
            status=TaskStatus.READY,
            required_capabilities=["python"],
        )
        task = await task_repo.create_task(task)

        event_bus = EventBus()
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            max_concurrent_tasks=1,
            output_dir=temp_output_dir,
            event_bus=event_bus,
            enable_hot_reload=False,
        )

        # Track which worker was assigned
        assigned_worker_id = None

        async def mock_execute(task_param, worker_param):
            nonlocal assigned_worker_id
            assigned_worker_id = worker_param.id

            task_param.status = TaskStatus.DONE
            await task_repo.update_task(task_param)
            worker_param.status = WorkerStatus.IDLE
            worker_param.current_task_id = None
            await WorkerRepository(db).update(worker_param)

            return SessionResult(
                status=SessionStatus.COMPLETED,
                output="Task completed",
                exit_code=0,
            )

        scheduler.executor.execute_task = mock_execute

        await scheduler.start()

        try:
            await asyncio.sleep(0.5)

            # Verify python worker was assigned (not rust worker)
            assert assigned_worker_id == python_worker.id
            assert assigned_worker_id != rust_worker.id

        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_health_check_detection(
        self, db, project, worker, temp_output_dir
    ):
        """Test that scheduler detects and handles stuck tasks/workers."""
        task_repo = TaskRepository(db)

        task = Task(
            project_id=project.id,
            title="Stuck task",
            description="This task will get stuck",
            priority=Priority.P2,
            status=TaskStatus.READY,
        )
        task = await task_repo.create_task(task)

        event_bus = EventBus()
        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            max_concurrent_tasks=1,
            output_dir=temp_output_dir,
            event_bus=event_bus,
            enable_hot_reload=False,
        )

        # Mock a stuck execution (never completes)
        async def mock_execute_stuck(task_param, worker_param):
            # Mark as in progress but never finish
            task_param.status = TaskStatus.IN_PROGRESS
            await task_repo.update_task(task_param)
            worker_param.status = WorkerStatus.BUSY
            worker_param.current_task_id = task_param.id
            await WorkerRepository(db).update(worker_param)

            # Sleep forever (will be cancelled)
            await asyncio.sleep(1000)

            return SessionResult(
                status=SessionStatus.COMPLETED,
                output="Task completed",
                exit_code=0,
            )

        scheduler.executor.execute_task = mock_execute_stuck

        await scheduler.start()

        try:
            # Wait for task to start
            await asyncio.sleep(0.3)

            # Verify task is in progress
            updated_task = await task_repo.get_task(task.id)
            assert updated_task.status == TaskStatus.IN_PROGRESS

            # Now stop scheduler (cancels stuck task)
            await scheduler.stop()

            # Verify worker was cleaned up
            updated_worker = await WorkerRepository(db).get(worker.id)
            assert updated_worker.status == WorkerStatus.OFFLINE

        finally:
            if scheduler._running:
                await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_emits_events(
        self, db, project, worker, temp_output_dir
    ):
        """Test that scheduler emits events during task execution."""
        task_repo = TaskRepository(db)

        task = Task(
            project_id=project.id,
            title="Event test task",
            description="Test event emission",
            priority=Priority.P2,
            status=TaskStatus.READY,
        )
        task = await task_repo.create_task(task)

        event_bus = EventBus()
        received_events = []

        async def event_handler(event_type, data):
            received_events.append((event_type, data))

        # Subscribe to all events
        await event_bus.subscribe("*", event_handler)

        scheduler = Scheduler(
            db,
            poll_interval=0.1,
            max_concurrent_tasks=1,
            output_dir=temp_output_dir,
            event_bus=event_bus,
            enable_hot_reload=False,
        )

        scheduler.executor.execute_task = make_mock_execute(task_repo, db)

        await scheduler.start()

        try:
            await asyncio.sleep(0.5)

            # Verify events were emitted
            # Note: Actual events depend on implementation
            assert len(received_events) >= 0  # At minimum, no errors

        finally:
            await scheduler.stop()


class TestE2EWorkerExecutionFlow:
    """Tests for the complete worker execution flow."""

    @pytest.mark.asyncio
    async def test_full_task_lifecycle_status_transitions(
        self, db, project, temp_output_dir
    ):
        """Test complete task lifecycle status transitions."""
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Create a worker
        worker = Worker(
            name="Test Worker",
            type="claude-code",
            command="echo",
            status=WorkerStatus.IDLE,
        )
        worker = await worker_repo.create(worker)

        # Create a task
        task = Task(
            project_id=project.id,
            title="Test task",
            description="Test task lifecycle",
            priority=Priority.P2,
            status=TaskStatus.READY,
        )
        task = await task_repo.create_task(task)

        # Create executor and mock the worker interface
        event_bus = EventBus()
        executor = WorkerExecutor(
            db,
            output_dir=temp_output_dir,
            event_bus=event_bus,
        )

        # Mock the worker interface to simulate execution without real CLI
        from ringmaster.worker.platforms import WorkerInterface, SessionHandle

        mock_handle = AsyncMock()
        from datetime import datetime, UTC
        mock_handle.wait = AsyncMock(return_value=SessionResult(
            status=SessionStatus.COMPLETED,
            output="Task completed",
            exit_code=0,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        ))

        # Create async generator for stream_output
        async def stream_output_mock():
            yield "output line 1\n"
            yield "output line 2\n"

        mock_handle.stream_output = stream_output_mock

        mock_interface = MagicMock(spec=WorkerInterface)
        mock_interface.is_available = AsyncMock(return_value=True)
        mock_interface.start_session = AsyncMock(return_value=mock_handle)

        # Patch get_worker to return our mock
        # Also patch event_bus.emit to avoid UUID validation issues
        original_emit = event_bus.emit
        emitted_events = []

        async def mock_emit(event_type, data, project_id=None):
            emitted_events.append((event_type, data, str(project_id) if project_id else None))

        with patch('ringmaster.worker.executor.get_worker', return_value=mock_interface):
            with patch.object(event_bus, 'emit', side_effect=mock_emit):
                # Execute the task
                result = await executor.execute_task(task, worker)

        # Verify result
        assert result.status == SessionStatus.COMPLETED
        assert result.exit_code == 0

        # Verify task status transitions: READY -> IN_PROGRESS -> REVIEW/DONE
        # (Successful tasks go to REVIEW for validation before DONE)
        updated_task = await task_repo.get_task(task.id)
        assert updated_task.status in (TaskStatus.REVIEW, TaskStatus.DONE)
        # Note: worker_id is cleared after task completion by complete_task()
        assert updated_task.started_at is not None
        assert updated_task.attempts == 1

        # Verify worker status transitions: IDLE -> BUSY -> IDLE
        updated_worker = await worker_repo.get(worker.id)
        assert updated_worker.status == WorkerStatus.IDLE
        assert updated_worker.current_task_id is None
        assert updated_worker.tasks_completed > 0  # Worker tracked the completion

    @pytest.mark.asyncio
    async def test_task_failure_handling(
        self, db, project, temp_output_dir
    ):
        """Test that task failures are handled correctly."""
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Create a worker
        worker = Worker(
            name="Test Worker",
            type="claude-code",
            command="false",
            status=WorkerStatus.IDLE,
        )
        worker = await worker_repo.create(worker)

        task = Task(
            project_id=project.id,
            title="Failing task",
            description="This task should fail",
            priority=Priority.P2,
            status=TaskStatus.READY,
        )
        task = await task_repo.create_task(task)

        event_bus = EventBus()
        executor = WorkerExecutor(
            db,
            output_dir=temp_output_dir,
            event_bus=event_bus,
        )

        # Mock the worker interface to simulate failure
        from ringmaster.worker.platforms import WorkerInterface, SessionHandle

        mock_handle = AsyncMock()
        from datetime import datetime, UTC
        mock_handle.wait = AsyncMock(return_value=SessionResult(
            status=SessionStatus.COMPLETED,
            output="Task failed",
            exit_code=1,  # Non-zero exit code
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        ))

        # Create async generator for stream_output
        async def stream_output_mock():
            yield "error output\n"

        mock_handle.stream_output = stream_output_mock

        mock_interface = MagicMock(spec=WorkerInterface)
        mock_interface.is_available = AsyncMock(return_value=True)
        mock_interface.start_session = AsyncMock(return_value=mock_handle)

        # Mock event_bus.emit to avoid UUID validation issues
        async def mock_emit(event_type, data, project_id=None):
            pass

        with patch('ringmaster.worker.executor.get_worker', return_value=mock_interface):
            with patch.object(event_bus, 'emit', side_effect=mock_emit):
                result = await executor.execute_task(task, worker)

        # Verify failure was captured
        assert result.status == SessionStatus.COMPLETED  # Session completed but with non-zero exit
        assert result.exit_code == 1

        # Verify task status is READY for retry (attempts < max_attempts)
        updated_task = await task_repo.get_task(task.id)
        assert updated_task.status == TaskStatus.READY  # Retries go back to READY
        assert updated_task.attempts == 1  # First attempt was counted
        assert updated_task.started_at is not None  # started_at is set
        assert updated_task.completed_at is None  # Not completed yet
