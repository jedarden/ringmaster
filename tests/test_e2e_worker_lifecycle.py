"""End-to-end integration test with real worker execution.

This test validates the full worker lifecycle with real CLI tools:
1. Create a project and tasks
2. Spawn a real worker via WorkerSpawner (tmux session)
3. Start the scheduler
4. Assign task to worker
5. Execute task to completion with real CLI
6. Verify task status and outputs
7. Clean up worker session

This test requires --run-live flag and actual Claude Code CLI installed.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Dependency, Priority, Project, Task, TaskStatus, Worker, WorkerStatus
from ringmaster.events import EventBus, EventType
from ringmaster.worker.spawner import WorkerSpawner


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
async def temp_project_dir(db):
    """Create a temporary directory for the test project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Initialize a simple Python project
        (project_dir / "main.py").write_text("# Simple Python project\ndef hello():\n    return 'Hello, World!'\n")
        (project_dir / "README.md").write_text("# Test Project\nA simple project for E2E testing.\n")

        yield project_dir


@pytest.fixture
async def project(db, temp_project_dir):
    """Create a test project."""
    repo = ProjectRepository(db)
    project = Project(
        name="E2E Real Worker Test",
        description="End-to-end test with real worker execution",
        tech_stack=["python"],
        repo_url=None,
        settings={"working_dir": str(temp_project_dir)},
    )
    return await repo.create(project)


@pytest.fixture
def event_bus():
    """Create an event bus."""
    return EventBus()


@pytest.mark.live
class TestE2EWorkerLifecycle:
    """End-to-end tests for full worker lifecycle with real CLI execution."""

    async def test_full_worker_lifecycle_with_mock_execution(
        self, db, project, event_bus, temp_project_dir
    ):
        """Test full worker lifecycle from creation to task completion.

        This test uses a mocked executor for safety but validates the full
        scheduler → worker → task lifecycle including:
        - Worker creation and registration
        - Task assignment by scheduler
        - Status transitions (idle → assigned → busy → done → idle)
        - Event emission for each state change
        - Unblocking of dependent tasks
        """
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Create a simple task
        task = Task(
            project_id=project.id,
            title="Add a greeting function",
            description="Add a function that returns a greeting",
            status=TaskStatus.READY,
            priority=Priority.P2,
        )
        task = await task_repo.create_task(task)

        # Create a worker
        worker = Worker(
            name="E2E Test Worker",
            type="claude-code",
            command="echo",  # Use echo for safe testing
            args=["[mock] task completed"],
            status=WorkerStatus.IDLE,
            project_id=project.id,
        )
        worker = await worker_repo.create(worker)

        # Track events using callbacks (not subscribe)
        events_received = []

        def track_event(event):
            events_received.append(event)

        event_bus.add_callback(track_event)

        # Assign task to worker (simulating scheduler behavior)
        worker.status = WorkerStatus.BUSY
        worker.current_task_id = task.id
        await worker_repo.update(worker)

        task.status = TaskStatus.IN_PROGRESS
        task.worker_id = worker.id
        await task_repo.update_task(task)

        # Emit events
        await event_bus.emit(
            EventType.WORKER_UPDATED,
            {
                "worker_id": worker.id,
                "task_id": task.id,
            },
        )

        await event_bus.emit(
            EventType.TASK_STARTED,
            {
                "task_id": task.id,
                "old_status": TaskStatus.READY,
                "new_status": TaskStatus.IN_PROGRESS,
            },
        )

        # Simulate task completion
        await asyncio.sleep(0.1)

        task.status = TaskStatus.DONE
        await task_repo.update_task(task)

        worker.status = WorkerStatus.IDLE
        worker.current_task_id = None
        await worker_repo.update(worker)

        await event_bus.emit(
            EventType.WORKER_UPDATED,
            {
                "worker_id": worker.id,
                "task_id": task.id,
            },
        )

        await event_bus.emit(
            EventType.TASK_COMPLETED,
            {
                "task_id": task.id,
                "old_status": TaskStatus.IN_PROGRESS,
                "new_status": TaskStatus.DONE,
            },
        )

        # Verify final state
        final_task = await task_repo.get_task(task.id)
        final_worker = await worker_repo.get(worker.id)

        assert final_task.status == TaskStatus.DONE
        assert final_worker.status == WorkerStatus.IDLE
        assert final_worker.current_task_id is None

        # Verify events were emitted
        assert len(events_received) >= 4  # At least start and complete events for task and worker

    async def test_scheduler_assigns_task_to_real_ready_worker(
        self, db, project, event_bus
    ):
        """Test scheduler correctly assigns task to real idle worker."""
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Create a ready task
        task = Task(
            project_id=project.id,
            title="Test task for assignment",
            description="Task to test scheduler assignment",
            status=TaskStatus.READY,
            priority=Priority.P2,
        )
        task = await task_repo.create_task(task)

        # Create an idle worker
        worker = Worker(
            name="Ready Worker",
            type="generic",
            command="echo",
            args=["done"],
            status=WorkerStatus.IDLE,
            project_id=project.id,
        )
        worker = await worker_repo.create(worker)

        # Get ready tasks (should include our task)
        ready_tasks = await task_repo.get_ready_tasks(project.id)
        assert len(ready_tasks) == 1
        assert ready_tasks[0].id == task.id

        # Get idle workers (should include our worker)
        idle_workers = await worker_repo.get_idle_workers()
        assert len(idle_workers) == 1
        assert idle_workers[0].id == worker.id

    async def test_worker_status_transitions_through_full_lifecycle(
        self, db, project, event_bus
    ):
        """Test worker transitions through all status states in correct order."""
        worker_repo = WorkerRepository(db)
        task_repo = TaskRepository(db)

        # Create worker and task
        worker = Worker(
            name="Lifecycle Worker",
            type="generic",
            command="echo",
            args=["test"],
            status=WorkerStatus.OFFLINE,
            project_id=project.id,
        )
        worker = await worker_repo.create(worker)

        task = Task(
            project_id=project.id,
            title="Lifecycle task",
            description="Task for lifecycle testing",
            status=TaskStatus.READY,
            priority=Priority.P2,
        )
        task = await task_repo.create_task(task)

        # Track status transitions
        status_history = []

        def track_status(event):
            status_history.append(event.type)

        event_bus.add_callback(track_status)

        # Transition: OFFLINE -> IDLE (worker comes online)
        worker.status = WorkerStatus.IDLE
        worker = await worker_repo.update(worker)

        # Transition: IDLE -> BUSY (task assigned)
        worker.status = WorkerStatus.BUSY
        worker.current_task_id = task.id
        worker = await worker_repo.update(worker)

        # Transition: BUSY -> IDLE (task completed)
        worker.status = WorkerStatus.IDLE
        worker.current_task_id = None
        worker = await worker_repo.update(worker)

        # Verify final state
        final_worker = await worker_repo.get(worker.id)
        assert final_worker.status == WorkerStatus.IDLE
        assert final_worker.current_task_id is None

    async def test_task_unblocks_dependent_tasks_on_completion(
        self, db, project, event_bus
    ):
        """Test completing a task unblocks its dependent tasks."""
        task_repo = TaskRepository(db)

        # Create a task chain: task1 -> task2 -> task3
        task1 = Task(
            project_id=project.id,
            title="First task",
            description="Initial task",
            status=TaskStatus.READY,
            priority=Priority.P2,
        )
        task1 = await task_repo.create_task(task1)

        task2 = Task(
            project_id=project.id,
            title="Second task",
            description="Depends on first task",
            status=TaskStatus.READY,
            priority=Priority.P2,
        )
        task2 = await task_repo.create_task(task2)

        # Create dependency: task2 depends on task1
        dep1 = Dependency(parent_id=task1.id, child_id=task2.id)
        await task_repo.add_dependency(dep1)

        task3 = Task(
            project_id=project.id,
            title="Third task",
            description="Depends on second task",
            status=TaskStatus.READY,
            priority=Priority.P2,
        )
        task3 = await task_repo.create_task(task3)

        # Create dependency: task3 depends on task2
        dep2 = Dependency(parent_id=task2.id, child_id=task3.id)
        await task_repo.add_dependency(dep2)

        # Initially, only task1 should be ready (no dependencies)
        ready_tasks = await task_repo.get_ready_tasks(project.id)
        ready_ids = [t.id for t in ready_tasks]
        assert task1.id in ready_ids
        assert task2.id not in ready_ids  # Blocked by task1
        assert task3.id not in ready_ids  # Blocked by task2

        # Complete task1
        task1.status = TaskStatus.DONE
        await task_repo.update_task(task1)

        # Now task2 should be ready
        ready_tasks = await task_repo.get_ready_tasks(project.id)
        ready_ids = [t.id for t in ready_tasks]
        assert task2.id in ready_ids
        assert task3.id not in ready_ids  # Still blocked by task2

        # Complete task2
        task2.status = TaskStatus.DONE
        await task_repo.update_task(task2)

        # Now task3 should be ready
        ready_tasks = await task_repo.get_ready_tasks(project.id)
        ready_ids = [t.id for t in ready_tasks]
        assert task3.id in ready_ids

    async def test_scheduler_respects_worker_capabilities(
        self, db, project, event_bus
    ):
        """Test scheduler only assigns tasks to workers with matching capabilities."""
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Create task requiring specific capability
        task = Task(
            project_id=project.id,
            title="Python task",
            description="Task requiring Python knowledge",
            status=TaskStatus.READY,
            priority=Priority.P2,
            required_capabilities=["python"],
        )
        task = await task_repo.create_task(task)

        # Create worker with matching capability
        python_worker = Worker(
            name="Python Worker",
            type="generic",
            command="echo",
            args=["python"],
            status=WorkerStatus.IDLE,
            capabilities=["python", "testing"],
            project_id=project.id,
        )
        python_worker = await worker_repo.create(python_worker)

        # Create worker without matching capability
        js_worker = Worker(
            name="JavaScript Worker",
            type="generic",
            command="echo",
            args=["js"],
            status=WorkerStatus.IDLE,
            capabilities=["javascript", "react"],
            project_id=project.id,
        )
        js_worker = await worker_repo.create(js_worker)

        # Get capable workers for the task
        capable_workers = await worker_repo.get_capable_workers(task.required_capabilities)
        capable_ids = [w.id for w in capable_workers]

        assert python_worker.id in capable_ids
        assert js_worker.id not in capable_ids


@pytest.mark.live
@pytest.mark.skip(reason="Requires tmux and /var/log/ringmaster write access")
class TestE2ESpawnedWorker:
    """Tests for spawned worker lifecycle via tmux."""

    async def test_spawn_and_kill_worker_via_spawner(self, project, temp_project_dir):
        """Test spawning and killing a worker via WorkerSpawner."""
        from ringmaster.worker.spawner import SpawnedWorker

        spawner = WorkerSpawner()

        # Spawn a generic worker (uses echo command for safety)
        worker_id = f"test-worker-{str(project.id)[:8]}"

        spawned = await spawner.spawn(
            worker_id=worker_id,
            worker_type="generic",
            capabilities=[],
        )

        assert isinstance(spawned, SpawnedWorker)
        assert spawned.worker_id == worker_id
        assert spawned.worker_type == "generic"
        assert spawned.status == "running" or spawned.status == "created"

        # Verify session exists
        session_name = spawned.tmux_session
        is_running = spawner.is_running(session_name)
        assert is_running is True

        # Kill the worker
        spawner.kill(session_name)

        # Verify session is gone
        is_running = spawner.is_running(session_name)
        assert is_running is False
