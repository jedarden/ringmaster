"""Tests for database layer."""

import tempfile
from pathlib import Path

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Priority, Project, Task, Worker


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.disconnect()


@pytest.mark.asyncio
async def test_project_crud(db):
    """Test project CRUD operations."""
    repo = ProjectRepository(db)

    # Create
    project = Project(
        name="Test Project",
        description="A test project",
        tech_stack=["python"],
    )
    created = await repo.create(project)
    assert created.name == "Test Project"

    # Read
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.name == "Test Project"
    assert fetched.tech_stack == ["python"]

    # Update
    fetched.name = "Updated Project"
    updated = await repo.update(fetched)
    assert updated.name == "Updated Project"

    # List
    projects = await repo.list()
    assert len(projects) == 1

    # Delete
    deleted = await repo.delete(created.id)
    assert deleted is True
    assert await repo.get(created.id) is None


@pytest.mark.asyncio
async def test_task_crud(db):
    """Test task CRUD operations."""
    project_repo = ProjectRepository(db)
    task_repo = TaskRepository(db)

    # Create project first
    project = await project_repo.create(Project(name="Test"))

    # Create task
    task = Task(
        project_id=project.id,
        title="Test Task",
        description="A test task",
        priority=Priority.P1,
    )
    created = await task_repo.create_task(task)
    assert created.title == "Test Task"
    assert created.id.startswith("bd-")

    # Read
    fetched = await task_repo.get_task(created.id)
    assert fetched is not None
    assert fetched.title == "Test Task"

    # Update
    fetched.title = "Updated Task"
    updated = await task_repo.update_task(fetched)
    assert updated.title == "Updated Task"

    # List
    tasks = await task_repo.list_tasks(project_id=project.id)
    assert len(tasks) == 1

    # Delete
    deleted = await task_repo.delete_task(created.id)
    assert deleted is True


@pytest.mark.asyncio
async def test_worker_crud(db):
    """Test worker CRUD operations."""
    repo = WorkerRepository(db)

    # Create
    worker = Worker(
        name="Test Worker",
        type="claude-code",
        command="claude",
    )
    created = await repo.create(worker)
    assert created.name == "Test Worker"

    # Read
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.type == "claude-code"

    # List
    workers = await repo.list()
    assert len(workers) == 1

    # Delete
    deleted = await repo.delete(created.id)
    assert deleted is True


@pytest.mark.asyncio
async def test_task_dependencies(db):
    """Test task dependency management."""
    project_repo = ProjectRepository(db)
    task_repo = TaskRepository(db)

    # Create project
    project = await project_repo.create(Project(name="Test"))

    # Create two tasks
    task1 = await task_repo.create_task(
        Task(project_id=project.id, title="Task 1")
    )
    task2 = await task_repo.create_task(
        Task(project_id=project.id, title="Task 2")
    )

    # Add dependency: task2 depends on task1
    from ringmaster.domain import Dependency

    dep = Dependency(child_id=task2.id, parent_id=task1.id)
    await task_repo.add_dependency(dep)

    # Check dependencies
    deps = await task_repo.get_dependencies(task2.id)
    assert len(deps) == 1
    assert deps[0].parent_id == task1.id

    # Check dependents
    dependents = await task_repo.get_dependents(task1.id)
    assert len(dependents) == 1
    assert dependents[0].child_id == task2.id
