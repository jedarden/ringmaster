"""API integration tests."""

import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ringmaster.api.app import create_app
from ringmaster.db.connection import Database


@pytest.fixture
async def app_with_db() -> AsyncGenerator[tuple, None]:
    """Create an app with a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        await db.connect()

        app = create_app()
        app.state.db = db

        yield app, db

        await db.disconnect()


@pytest.fixture
async def client(app_with_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    app, _ = app_with_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for health endpoint."""

    async def test_health_check(self, client: AsyncClient):
        """Test health check returns healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"


class TestProjectsAPI:
    """Tests for projects API."""

    async def test_list_projects_empty(self, client: AsyncClient):
        """Test listing projects when none exist."""
        response = await client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_project(self, client: AsyncClient):
        """Test creating a project."""
        response = await client.post(
            "/api/projects",
            json={
                "name": "Test Project",
                "description": "A test project",
                "tech_stack": ["python", "fastapi"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == "A test project"
        assert data["tech_stack"] == ["python", "fastapi"]
        assert "id" in data

    async def test_get_project(self, client: AsyncClient):
        """Test getting a project by ID."""
        # Create first
        create_response = await client.post(
            "/api/projects",
            json={"name": "Get Project Test"},
        )
        project_id = create_response.json()["id"]

        # Get
        response = await client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Get Project Test"

    async def test_get_project_not_found(self, client: AsyncClient):
        """Test getting a non-existent project returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/projects/{fake_id}")
        assert response.status_code == 404

    async def test_update_project(self, client: AsyncClient):
        """Test updating a project."""
        # Create first
        create_response = await client.post(
            "/api/projects",
            json={"name": "Original Name"},
        )
        project_id = create_response.json()["id"]

        # Update
        response = await client.patch(
            f"/api/projects/{project_id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    async def test_delete_project(self, client: AsyncClient):
        """Test deleting a project."""
        # Create first
        create_response = await client.post(
            "/api/projects",
            json={"name": "To Delete"},
        )
        project_id = create_response.json()["id"]

        # Delete
        response = await client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/projects/{project_id}")
        assert response.status_code == 404


class TestTasksAPI:
    """Tests for tasks API."""

    async def test_list_tasks_empty(self, client: AsyncClient):
        """Test listing tasks when none exist."""
        response = await client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_task(self, client: AsyncClient):
        """Test creating a task."""
        # Create project first
        project_response = await client.post(
            "/api/projects",
            json={"name": "Task Test Project"},
        )
        project_id = project_response.json()["id"]

        # Create task
        response = await client.post(
            "/api/tasks",
            json={
                "project_id": project_id,
                "title": "Test Task",
                "description": "A test task",
                "priority": "P1",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Task"
        assert data["description"] == "A test task"
        assert data["priority"] == "P1"
        assert data["id"].startswith("bd-")

    async def test_create_epic(self, client: AsyncClient):
        """Test creating an epic."""
        # Create project first
        project_response = await client.post(
            "/api/projects",
            json={"name": "Epic Test Project"},
        )
        project_id = project_response.json()["id"]

        # Create epic
        response = await client.post(
            "/api/tasks/epics",
            json={
                "project_id": project_id,
                "title": "Test Epic",
                "acceptance_criteria": ["Feature complete", "Tests pass"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Epic"
        assert data["type"] == "epic"
        assert "Feature complete" in data["acceptance_criteria"]

    async def test_get_task(self, client: AsyncClient):
        """Test getting a task by ID."""
        # Create project and task
        project_response = await client.post(
            "/api/projects",
            json={"name": "Get Task Test Project"},
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Get Task Test"},
        )
        task_id = task_response.json()["id"]

        # Get
        response = await client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Get Task Test"

    async def test_get_task_not_found(self, client: AsyncClient):
        """Test getting a non-existent task returns 404."""
        response = await client.get("/api/tasks/bd-nonexistent")
        assert response.status_code == 404

    async def test_update_task(self, client: AsyncClient):
        """Test updating a task."""
        # Create project and task
        project_response = await client.post(
            "/api/projects",
            json={"name": "Update Task Test Project"},
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Original Title"},
        )
        task_id = task_response.json()["id"]

        # Update
        response = await client.patch(
            f"/api/tasks/{task_id}",
            json={"title": "Updated Title", "status": "in_progress"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["status"] == "in_progress"

    async def test_delete_task(self, client: AsyncClient):
        """Test deleting a task."""
        # Create project and task
        project_response = await client.post(
            "/api/projects",
            json={"name": "Delete Task Test Project"},
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "To Delete"},
        )
        task_id = task_response.json()["id"]

        # Delete
        response = await client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 404

    async def test_task_dependencies(self, client: AsyncClient):
        """Test adding and retrieving task dependencies."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects",
            json={"name": "Dependency Test Project"},
        )
        project_id = project_response.json()["id"]

        task1_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 1"},
        )
        task1_id = task1_response.json()["id"]

        task2_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 2"},
        )
        task2_id = task2_response.json()["id"]

        # Add dependency: task2 depends on task1
        response = await client.post(
            f"/api/tasks/{task2_id}/dependencies",
            json={"parent_id": task1_id},
        )
        assert response.status_code == 201

        # Check dependencies
        response = await client.get(f"/api/tasks/{task2_id}/dependencies")
        assert response.status_code == 200
        deps = response.json()
        assert len(deps) == 1
        assert deps[0]["parent_id"] == task1_id

        # Check dependents
        response = await client.get(f"/api/tasks/{task1_id}/dependents")
        assert response.status_code == 200
        dependents = response.json()
        assert len(dependents) == 1
        assert dependents[0]["child_id"] == task2_id

    async def test_filter_tasks_by_project(self, client: AsyncClient):
        """Test filtering tasks by project."""
        # Create two projects
        proj1_response = await client.post(
            "/api/projects", json={"name": "Project 1"}
        )
        proj1_id = proj1_response.json()["id"]

        proj2_response = await client.post(
            "/api/projects", json={"name": "Project 2"}
        )
        proj2_id = proj2_response.json()["id"]

        # Create tasks in each
        await client.post(
            "/api/tasks",
            json={"project_id": proj1_id, "title": "Task in P1"},
        )
        await client.post(
            "/api/tasks",
            json={"project_id": proj2_id, "title": "Task in P2"},
        )

        # Filter by project 1
        response = await client.get(f"/api/tasks?project_id={proj1_id}")
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Task in P1"

    async def test_filter_tasks_by_status(self, client: AsyncClient):
        """Test filtering tasks by status."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects", json={"name": "Status Filter Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Open Task"},
        )
        task_id = task_response.json()["id"]

        # Update one to in_progress
        await client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "in_progress"},
        )

        # Create another task (will be open)
        await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Another Open Task"},
        )

        # Filter by status
        response = await client.get("/api/tasks?status=in_progress")
        tasks = response.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Open Task"


class TestWorkersAPI:
    """Tests for workers API - testing routes/workers.py."""

    async def test_list_workers_empty(self, client: AsyncClient):
        """Test listing workers when none exist."""
        response = await client.get("/api/workers")
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_worker(self, client: AsyncClient):
        """Test creating a worker."""
        response = await client.post(
            "/api/workers",
            json={
                "name": "Test Worker",
                "type": "claude-code",
                "command": "claude",
                "args": ["--print"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Worker"
        assert data["type"] == "claude-code"
        assert data["command"] == "claude"

    async def test_get_worker(self, client: AsyncClient):
        """Test getting a worker by ID."""
        # Create first
        create_response = await client.post(
            "/api/workers",
            json={"name": "Get Worker Test", "type": "aider", "command": "aider"},
        )
        worker_id = create_response.json()["id"]

        # Get
        response = await client.get(f"/api/workers/{worker_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Get Worker Test"

    async def test_update_worker(self, client: AsyncClient):
        """Test updating a worker."""
        # Create first
        create_response = await client.post(
            "/api/workers",
            json={"name": "Original Worker", "type": "codex", "command": "codex"},
        )
        worker_id = create_response.json()["id"]

        # Update
        response = await client.patch(
            f"/api/workers/{worker_id}",
            json={"name": "Updated Worker"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Worker"

    async def test_delete_worker(self, client: AsyncClient):
        """Test deleting a worker."""
        # Create first
        create_response = await client.post(
            "/api/workers",
            json={"name": "To Delete", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Delete
        response = await client.delete(f"/api/workers/{worker_id}")
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/workers/{worker_id}")
        assert response.status_code == 404

    async def test_activate_worker(self, client: AsyncClient):
        """Test activating a worker."""
        # Create first
        create_response = await client.post(
            "/api/workers",
            json={"name": "Activate Test", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Activate
        response = await client.post(f"/api/workers/{worker_id}/activate")
        assert response.status_code == 200
        assert response.json()["status"] == "idle"

    async def test_deactivate_worker(self, client: AsyncClient):
        """Test deactivating a worker."""
        # Create first
        create_response = await client.post(
            "/api/workers",
            json={"name": "Deactivate Test", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Activate first
        await client.post(f"/api/workers/{worker_id}/activate")

        # Deactivate
        response = await client.post(f"/api/workers/{worker_id}/deactivate")
        assert response.status_code == 200
        assert response.json()["status"] == "offline"


class TestQueueAPI:
    """Tests for queue API - testing routes/queue.py."""

    async def test_queue_stats(self, client: AsyncClient):
        """Test queue stats endpoint."""
        response = await client.get("/api/queue/stats")
        assert response.status_code == 200
        data = response.json()
        # Should have expected fields
        assert "ready_tasks" in data
        assert "assigned_tasks" in data
        assert "in_progress_tasks" in data
        assert "idle_workers" in data
        assert "busy_workers" in data
        # All should be 0 for empty db
        assert data["ready_tasks"] == 0
        assert data["idle_workers"] == 0

    async def test_get_ready_tasks(self, client: AsyncClient):
        """Test getting ready tasks."""
        response = await client.get("/api/queue/ready")
        assert response.status_code == 200
        assert response.json() == []

    async def test_enqueue_task(self, client: AsyncClient):
        """Test enqueueing a task."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Queue Test Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Queue Test Task"},
        )
        task_id = task_response.json()["id"]

        # Enqueue
        response = await client.post(
            "/api/queue/enqueue",
            json={"task_id": task_id},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "enqueued"

        # Verify stats updated
        stats_response = await client.get("/api/queue/stats")
        assert stats_response.json()["ready_tasks"] == 1

    async def test_complete_task(self, client: AsyncClient):
        """Test completing a task."""
        # Create and enqueue task
        project_response = await client.post(
            "/api/projects", json={"name": "Complete Test Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Complete Test Task"},
        )
        task_id = task_response.json()["id"]

        await client.post(
            "/api/queue/enqueue",
            json={"task_id": task_id},
        )

        # Complete
        response = await client.post(
            "/api/queue/complete",
            json={"task_id": task_id, "success": True},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    async def test_recalculate_priorities(self, client: AsyncClient):
        """Test recalculating priorities."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Priority Test Project"}
        )
        project_id = project_response.json()["id"]

        # Create tasks
        await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 1"},
        )
        await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 2"},
        )

        # Recalculate
        response = await client.post(
            "/api/queue/recalculate",
            json={"project_id": project_id},
        )
        assert response.status_code == 200
        assert "tasks_updated" in response.json()
