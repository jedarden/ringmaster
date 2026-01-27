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

    async def test_get_project_summary(self, client: AsyncClient):
        """Test getting a project summary."""
        # Create a project
        create_response = await client.post(
            "/api/projects",
            json={"name": "Summary Test Project"},
        )
        project_id = create_response.json()["id"]

        # Get summary
        response = await client.get(f"/api/projects/{project_id}/summary")
        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "project" in data
        assert data["project"]["name"] == "Summary Test Project"
        assert "task_counts" in data
        assert "total_tasks" in data
        assert "active_workers" in data
        assert "pending_decisions" in data
        assert "pending_questions" in data
        assert "latest_activity" in data

        # No tasks yet
        assert data["total_tasks"] == 0
        assert data["active_workers"] == 0
        assert data["pending_decisions"] == 0

    async def test_get_project_summary_with_tasks(self, client: AsyncClient):
        """Test getting a project summary with tasks."""
        # Create a project
        create_response = await client.post(
            "/api/projects",
            json={"name": "Summary With Tasks"},
        )
        project_id = create_response.json()["id"]

        # Create some tasks and update their statuses
        task1_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 1"},
        )
        task1_id = task1_response.json()["id"]
        await client.patch(f"/api/tasks/{task1_id}", json={"status": "ready"})

        task2_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 2"},
        )
        task2_id = task2_response.json()["id"]
        await client.patch(f"/api/tasks/{task2_id}", json={"status": "in_progress"})

        task3_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task 3"},
        )
        task3_id = task3_response.json()["id"]
        await client.patch(f"/api/tasks/{task3_id}", json={"status": "done"})

        # Get summary
        response = await client.get(f"/api/projects/{project_id}/summary")
        assert response.status_code == 200
        data = response.json()

        # Check task counts
        assert data["total_tasks"] == 3
        assert data["task_counts"]["ready"] == 1
        assert data["task_counts"]["in_progress"] == 1
        assert data["task_counts"]["done"] == 1

    async def test_get_project_summary_with_decisions(self, client: AsyncClient):
        """Test getting a project summary with pending decisions."""
        # Create a project
        create_response = await client.post(
            "/api/projects",
            json={"name": "Summary With Decisions"},
        )
        project_id = create_response.json()["id"]

        # Create a task
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task With Decision"},
        )
        task_id = task_response.json()["id"]

        # Create a decision blocking the task
        await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "What approach should we use?",
                "options": ["Option A", "Option B"],
            },
        )

        # Get summary
        response = await client.get(f"/api/projects/{project_id}/summary")
        assert response.status_code == 200
        data = response.json()

        assert data["pending_decisions"] == 1

    async def test_get_project_summary_not_found(self, client: AsyncClient):
        """Test getting summary for non-existent project."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/projects/{fake_id}/summary")
        assert response.status_code == 404

    async def test_list_projects_with_summaries(self, client: AsyncClient):
        """Test listing all projects with summaries."""
        # Create a project with some activity
        create_response = await client.post(
            "/api/projects",
            json={"name": "Project With Activity"},
        )
        project_id = create_response.json()["id"]

        # Add a task and update its status
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Some Task"},
        )
        task_id = task_response.json()["id"]
        await client.patch(f"/api/tasks/{task_id}", json={"status": "ready"})

        # Create another project without activity
        await client.post(
            "/api/projects",
            json={"name": "Empty Project"},
        )

        # Get projects with summaries
        response = await client.get("/api/projects/with-summaries")
        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2

        # Find the project with activity (most recent first)
        project_with_activity = next(
            s for s in data if s["project"]["name"] == "Project With Activity"
        )
        assert project_with_activity["total_tasks"] == 1
        assert project_with_activity["task_counts"]["ready"] == 1

        # Find the empty project
        empty_project = next(
            s for s in data if s["project"]["name"] == "Empty Project"
        )
        assert empty_project["total_tasks"] == 0


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

    async def test_remove_task_dependency(self, client: AsyncClient):
        """Test removing a task dependency."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects",
            json={"name": "Remove Dependency Test"},
        )
        project_id = project_response.json()["id"]

        task1_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Parent Task"},
        )
        task1_id = task1_response.json()["id"]

        task2_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Child Task"},
        )
        task2_id = task2_response.json()["id"]

        # Add dependency: task2 depends on task1
        await client.post(
            f"/api/tasks/{task2_id}/dependencies",
            json={"parent_id": task1_id},
        )

        # Verify dependency exists
        response = await client.get(f"/api/tasks/{task2_id}/dependencies")
        assert len(response.json()) == 1

        # Remove dependency
        response = await client.delete(
            f"/api/tasks/{task2_id}/dependencies/{task1_id}"
        )
        assert response.status_code == 200
        assert response.json()["removed"] is True

        # Verify dependency removed
        response = await client.get(f"/api/tasks/{task2_id}/dependencies")
        assert len(response.json()) == 0

    async def test_remove_nonexistent_dependency(self, client: AsyncClient):
        """Test removing a dependency that doesn't exist returns 404."""
        # Create project and task
        project_response = await client.post(
            "/api/projects",
            json={"name": "Nonexistent Dependency Test"},
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Orphan Task"},
        )
        task_id = task_response.json()["id"]

        # Try to remove nonexistent dependency
        response = await client.delete(
            f"/api/tasks/{task_id}/dependencies/nonexistent-parent"
        )
        assert response.status_code == 404

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

    async def test_assign_task_to_worker(self, client: AsyncClient):
        """Test assigning a task to an idle worker."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Assign Test Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task to Assign"},
        )
        task_id = task_response.json()["id"]

        # Create worker
        worker_response = await client.post(
            "/api/workers",
            json={
                "name": "Test Worker",
                "type": "test",
                "command": "echo",
            },
        )
        worker_id = worker_response.json()["id"]

        # Activate worker (make it idle)
        await client.post(f"/api/workers/{worker_id}/activate")

        # Assign task to worker
        response = await client.post(
            f"/api/tasks/{task_id}/assign",
            json={"worker_id": worker_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] == worker_id
        assert data["status"] == "assigned"

        # Verify worker is now busy
        worker_response = await client.get(f"/api/workers/{worker_id}")
        worker = worker_response.json()
        assert worker["status"] == "busy"
        assert worker["current_task_id"] == task_id

    async def test_unassign_task_from_worker(self, client: AsyncClient):
        """Test unassigning a task from a worker."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Unassign Test Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task to Unassign"},
        )
        task_id = task_response.json()["id"]

        # Create and activate worker
        worker_response = await client.post(
            "/api/workers",
            json={"name": "Test Worker", "type": "test", "command": "echo"},
        )
        worker_id = worker_response.json()["id"]
        await client.post(f"/api/workers/{worker_id}/activate")

        # Assign then unassign
        await client.post(
            f"/api/tasks/{task_id}/assign",
            json={"worker_id": worker_id},
        )
        response = await client.post(
            f"/api/tasks/{task_id}/assign",
            json={"worker_id": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] is None
        assert data["status"] == "ready"

        # Verify worker is idle
        worker_response = await client.get(f"/api/workers/{worker_id}")
        worker = worker_response.json()
        assert worker["status"] == "idle"
        assert worker["current_task_id"] is None

    async def test_assign_task_to_offline_worker_fails(self, client: AsyncClient):
        """Test that assigning to an offline worker fails."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Offline Worker Test"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task for Offline"},
        )
        task_id = task_response.json()["id"]

        # Create worker (offline by default)
        worker_response = await client.post(
            "/api/workers",
            json={"name": "Offline Worker", "type": "test", "command": "echo"},
        )
        worker_id = worker_response.json()["id"]

        # Try to assign - should fail
        response = await client.post(
            f"/api/tasks/{task_id}/assign",
            json={"worker_id": worker_id},
        )
        assert response.status_code == 400
        assert "offline" in response.json()["detail"].lower()

    async def test_assign_task_to_busy_worker_fails(self, client: AsyncClient):
        """Test that assigning to a busy worker fails."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects", json={"name": "Busy Worker Test"}
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

        # Create and activate worker
        worker_response = await client.post(
            "/api/workers",
            json={"name": "Busy Worker", "type": "test", "command": "echo"},
        )
        worker_id = worker_response.json()["id"]
        await client.post(f"/api/workers/{worker_id}/activate")

        # Assign first task
        await client.post(
            f"/api/tasks/{task1_id}/assign",
            json={"worker_id": worker_id},
        )

        # Try to assign second task - should fail
        response = await client.post(
            f"/api/tasks/{task2_id}/assign",
            json={"worker_id": worker_id},
        )
        assert response.status_code == 400
        assert "busy" in response.json()["detail"].lower()

    async def test_assign_epic_fails(self, client: AsyncClient):
        """Test that epics cannot be assigned to workers."""
        # Create project and epic
        project_response = await client.post(
            "/api/projects", json={"name": "Epic Assign Test"}
        )
        project_id = project_response.json()["id"]

        epic_response = await client.post(
            "/api/tasks/epics",
            json={"project_id": project_id, "title": "Test Epic"},
        )
        epic_id = epic_response.json()["id"]

        # Create and activate worker
        worker_response = await client.post(
            "/api/workers",
            json={"name": "Epic Worker", "type": "test", "command": "echo"},
        )
        worker_id = worker_response.json()["id"]
        await client.post(f"/api/workers/{worker_id}/activate")

        # Try to assign epic - should fail
        response = await client.post(
            f"/api/tasks/{epic_id}/assign",
            json={"worker_id": worker_id},
        )
        assert response.status_code == 400
        assert "epic" in response.json()["detail"].lower()

    async def test_bulk_update_status(self, client: AsyncClient):
        """Test bulk updating task status."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects", json={"name": "Bulk Update Test"}
        )
        project_id = project_response.json()["id"]

        task_ids = []
        for i in range(3):
            task_response = await client.post(
                "/api/tasks",
                json={"project_id": project_id, "title": f"Bulk Task {i}"},
            )
            task_ids.append(task_response.json()["id"])

        # Bulk update status
        response = await client.post(
            "/api/tasks/bulk-update",
            json={"task_ids": task_ids, "status": "in_progress"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 3
        assert data["failed"] == 0

        # Verify all tasks updated
        for task_id in task_ids:
            task_response = await client.get(f"/api/tasks/{task_id}")
            assert task_response.json()["status"] == "in_progress"

    async def test_bulk_update_priority(self, client: AsyncClient):
        """Test bulk updating task priority."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects", json={"name": "Bulk Priority Test"}
        )
        project_id = project_response.json()["id"]

        task_ids = []
        for i in range(2):
            task_response = await client.post(
                "/api/tasks",
                json={"project_id": project_id, "title": f"Priority Task {i}"},
            )
            task_ids.append(task_response.json()["id"])

        # Bulk update priority
        response = await client.post(
            "/api/tasks/bulk-update",
            json={"task_ids": task_ids, "priority": "P0"},
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 2

        # Verify
        for task_id in task_ids:
            task_response = await client.get(f"/api/tasks/{task_id}")
            assert task_response.json()["priority"] == "P0"

    async def test_bulk_delete(self, client: AsyncClient):
        """Test bulk deleting tasks."""
        # Create project and tasks
        project_response = await client.post(
            "/api/projects", json={"name": "Bulk Delete Test"}
        )
        project_id = project_response.json()["id"]

        task_ids = []
        for i in range(3):
            task_response = await client.post(
                "/api/tasks",
                json={"project_id": project_id, "title": f"Delete Task {i}"},
            )
            task_ids.append(task_response.json()["id"])

        # Bulk delete
        response = await client.post(
            "/api/tasks/bulk-delete",
            json={"task_ids": task_ids},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 3
        assert data["failed"] == 0

        # Verify all deleted
        for task_id in task_ids:
            task_response = await client.get(f"/api/tasks/{task_id}")
            assert task_response.status_code == 404

    async def test_bulk_update_with_invalid_task(self, client: AsyncClient):
        """Test bulk update handles invalid task IDs gracefully."""
        # Create project and one valid task
        project_response = await client.post(
            "/api/projects", json={"name": "Partial Bulk Test"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Valid Task"},
        )
        valid_task_id = task_response.json()["id"]

        # Bulk update with mix of valid and invalid
        response = await client.post(
            "/api/tasks/bulk-update",
            json={"task_ids": [valid_task_id, "invalid-id"], "status": "done"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 1
        assert data["failed"] == 1
        assert len(data["errors"]) == 1


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

    async def test_create_worker_with_capabilities(self, client: AsyncClient):
        """Test creating a worker with capabilities."""
        response = await client.post(
            "/api/workers",
            json={
                "name": "Capable Worker",
                "type": "claude-code",
                "command": "claude",
                "capabilities": ["python", "typescript", "security"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Capable Worker"
        assert data["capabilities"] == ["python", "typescript", "security"]

    async def test_update_worker_capabilities(self, client: AsyncClient):
        """Test updating worker capabilities."""
        # Create worker with initial capabilities
        create_response = await client.post(
            "/api/workers",
            json={
                "name": "Update Caps Worker",
                "type": "aider",
                "command": "aider",
                "capabilities": ["python"],
            },
        )
        worker_id = create_response.json()["id"]

        # Update capabilities
        response = await client.patch(
            f"/api/workers/{worker_id}",
            json={"capabilities": ["python", "rust", "refactoring"]},
        )
        assert response.status_code == 200
        assert response.json()["capabilities"] == ["python", "rust", "refactoring"]

    async def test_get_worker_capabilities(self, client: AsyncClient):
        """Test getting worker capabilities."""
        # Create worker with capabilities
        create_response = await client.post(
            "/api/workers",
            json={
                "name": "Get Caps Worker",
                "type": "codex",
                "command": "codex",
                "capabilities": ["go", "kubernetes"],
            },
        )
        worker_id = create_response.json()["id"]

        # Get capabilities
        response = await client.get(f"/api/workers/{worker_id}/capabilities")
        assert response.status_code == 200
        assert response.json() == ["go", "kubernetes"]

    async def test_add_capability(self, client: AsyncClient):
        """Test adding a capability to a worker."""
        # Create worker with initial capabilities
        create_response = await client.post(
            "/api/workers",
            json={
                "name": "Add Cap Worker",
                "type": "claude-code",
                "command": "claude",
                "capabilities": ["python"],
            },
        )
        worker_id = create_response.json()["id"]

        # Add capability
        response = await client.post(
            f"/api/workers/{worker_id}/capabilities",
            json={"capability": "security"},
        )
        assert response.status_code == 201
        assert "security" in response.json()["capabilities"]
        assert "python" in response.json()["capabilities"]

    async def test_add_duplicate_capability(self, client: AsyncClient):
        """Test adding a duplicate capability doesn't create duplicates."""
        # Create worker with python capability
        create_response = await client.post(
            "/api/workers",
            json={
                "name": "Dup Cap Worker",
                "type": "claude-code",
                "command": "claude",
                "capabilities": ["python"],
            },
        )
        worker_id = create_response.json()["id"]

        # Add duplicate capability
        response = await client.post(
            f"/api/workers/{worker_id}/capabilities",
            json={"capability": "python"},
        )
        assert response.status_code == 201
        # Should still only have one "python"
        assert response.json()["capabilities"].count("python") == 1

    async def test_remove_capability(self, client: AsyncClient):
        """Test removing a capability from a worker."""
        # Create worker with multiple capabilities
        create_response = await client.post(
            "/api/workers",
            json={
                "name": "Remove Cap Worker",
                "type": "aider",
                "command": "aider",
                "capabilities": ["python", "typescript", "security"],
            },
        )
        worker_id = create_response.json()["id"]

        # Remove capability
        response = await client.delete(f"/api/workers/{worker_id}/capabilities/typescript")
        assert response.status_code == 200
        assert "typescript" not in response.json()["capabilities"]
        assert "python" in response.json()["capabilities"]
        assert "security" in response.json()["capabilities"]

    async def test_remove_nonexistent_capability(self, client: AsyncClient):
        """Test removing a capability that doesn't exist returns 404."""
        # Create worker
        create_response = await client.post(
            "/api/workers",
            json={
                "name": "No Cap Worker",
                "type": "codex",
                "command": "codex",
                "capabilities": ["python"],
            },
        )
        worker_id = create_response.json()["id"]

        # Try to remove capability that doesn't exist
        response = await client.delete(f"/api/workers/{worker_id}/capabilities/rust")
        assert response.status_code == 404

    async def test_cancel_worker_task(self, client: AsyncClient):
        """Test canceling a busy worker's task."""
        # Create project and task
        project_response = await client.post(
            "/api/projects",
            json={"name": "Cancel Test Project"},
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={
                "project_id": project_id,
                "title": "Task to cancel",
            },
        )
        task_id = task_response.json()["id"]

        # Create and activate worker (makes it idle)
        worker_response = await client.post(
            "/api/workers",
            json={
                "name": "Busy Worker",
                "type": "claude-code",
                "command": "claude",
            },
        )
        worker_id = worker_response.json()["id"]

        # Activate worker to make it idle (assignable)
        await client.post(f"/api/workers/{worker_id}/activate")

        # Assign task to worker - this makes the worker BUSY
        assign_resp = await client.post(
            f"/api/tasks/{task_id}/assign",
            json={"worker_id": worker_id},
        )
        assert assign_resp.status_code == 200

        # Verify worker is busy
        worker_check = await client.get(f"/api/workers/{worker_id}")
        assert worker_check.json()["status"] == "busy"

        # Cancel the worker's task
        response = await client.post(f"/api/workers/{worker_id}/cancel")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == task_id

        # Verify worker is now idle
        worker_response = await client.get(f"/api/workers/{worker_id}")
        assert worker_response.json()["status"] == "idle"

        # Verify task is marked as failed
        task_response = await client.get(f"/api/tasks/{task_id}")
        assert task_response.json()["status"] == "failed"

    async def test_cancel_worker_not_busy_fails(self, client: AsyncClient):
        """Test canceling a worker that's not busy returns error."""
        # Create idle worker
        worker_response = await client.post(
            "/api/workers",
            json={
                "name": "Idle Worker",
                "type": "aider",
                "command": "aider",
            },
        )
        worker_id = worker_response.json()["id"]

        # Activate worker (sets to idle)
        await client.post(f"/api/workers/{worker_id}/activate")

        # Try to cancel
        response = await client.post(f"/api/workers/{worker_id}/cancel")
        assert response.status_code == 400

    async def test_pause_worker(self, client: AsyncClient):
        """Test pausing an active worker."""
        # Create and activate worker
        worker_response = await client.post(
            "/api/workers",
            json={
                "name": "Pause Worker",
                "type": "claude-code",
                "command": "claude",
            },
        )
        worker_id = worker_response.json()["id"]

        await client.post(f"/api/workers/{worker_id}/activate")

        # Pause the worker
        response = await client.post(f"/api/workers/{worker_id}/pause")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["worker_id"] == worker_id

        # Verify worker is now offline (paused)
        worker_response = await client.get(f"/api/workers/{worker_id}")
        assert worker_response.json()["status"] == "offline"

    async def test_pause_offline_worker_fails(self, client: AsyncClient):
        """Test pausing an already offline worker returns error."""
        # Create worker (default is offline)
        worker_response = await client.post(
            "/api/workers",
            json={
                "name": "Offline Worker",
                "type": "goose",
                "command": "goose",
            },
        )
        worker_id = worker_response.json()["id"]

        # Try to pause
        response = await client.post(f"/api/workers/{worker_id}/pause")
        assert response.status_code == 400


class TestWorkerOutputAPI:
    """Tests for worker output streaming API."""

    async def test_get_worker_output_empty(self, client: AsyncClient):
        """Test getting output for a worker with no output."""
        # Create worker
        create_response = await client.post(
            "/api/workers",
            json={"name": "Output Test Worker", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Get output
        response = await client.get(f"/api/workers/{worker_id}/output")
        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] == worker_id
        assert data["lines"] == []
        assert data["total_lines"] == 0

    async def test_get_worker_output_not_found(self, client: AsyncClient):
        """Test getting output for non-existent worker returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/workers/{fake_id}/output")
        assert response.status_code == 404

    async def test_get_worker_output_with_buffer(self, client: AsyncClient):
        """Test getting output after writing to buffer."""
        from ringmaster.worker.output_buffer import output_buffer

        # Create worker
        create_response = await client.post(
            "/api/workers",
            json={"name": "Buffer Test Worker", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Write some output to the buffer
        await output_buffer.write(worker_id, "Line 1: Starting task...")
        await output_buffer.write(worker_id, "Line 2: Processing data...")
        await output_buffer.write(worker_id, "Line 3: Task complete!")

        # Get output
        response = await client.get(f"/api/workers/{worker_id}/output")
        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] == worker_id
        assert len(data["lines"]) == 3
        assert data["lines"][0]["line"] == "Line 1: Starting task..."
        assert data["lines"][0]["line_number"] == 1
        assert data["lines"][2]["line"] == "Line 3: Task complete!"
        assert data["lines"][2]["line_number"] == 3
        assert data["total_lines"] == 3

        # Cleanup
        await output_buffer.clear(worker_id)

    async def test_get_worker_output_since_line(self, client: AsyncClient):
        """Test getting output after a specific line number."""
        from ringmaster.worker.output_buffer import output_buffer

        # Create worker
        create_response = await client.post(
            "/api/workers",
            json={"name": "Since Line Worker", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Write some output
        await output_buffer.write(worker_id, "Line 1")
        await output_buffer.write(worker_id, "Line 2")
        await output_buffer.write(worker_id, "Line 3")
        await output_buffer.write(worker_id, "Line 4")

        # Get output since line 2
        response = await client.get(f"/api/workers/{worker_id}/output?since_line=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 2
        assert data["lines"][0]["line"] == "Line 3"
        assert data["lines"][0]["line_number"] == 3
        assert data["lines"][1]["line"] == "Line 4"
        assert data["lines"][1]["line_number"] == 4

        # Cleanup
        await output_buffer.clear(worker_id)

    async def test_get_worker_output_limit(self, client: AsyncClient):
        """Test limiting output lines."""
        from ringmaster.worker.output_buffer import output_buffer

        # Create worker
        create_response = await client.post(
            "/api/workers",
            json={"name": "Limit Worker", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        # Write many lines
        for i in range(10):
            await output_buffer.write(worker_id, f"Line {i + 1}")

        # Get only last 3 lines
        response = await client.get(f"/api/workers/{worker_id}/output?limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 3
        assert data["lines"][0]["line"] == "Line 8"
        assert data["lines"][2]["line"] == "Line 10"
        assert data["total_lines"] == 10

        # Cleanup
        await output_buffer.clear(worker_id)

    async def test_get_output_stats(self, client: AsyncClient):
        """Test getting output buffer statistics."""
        from ringmaster.worker.output_buffer import output_buffer

        # Create worker and write some output
        create_response = await client.post(
            "/api/workers",
            json={"name": "Stats Worker", "type": "test", "command": "test"},
        )
        worker_id = create_response.json()["id"]

        await output_buffer.write(worker_id, "Test line")

        # Get stats
        response = await client.get("/api/workers/output/stats")
        assert response.status_code == 200
        stats = response.json()
        assert worker_id in stats
        assert stats[worker_id]["line_count"] == 1
        assert stats[worker_id]["total_lines"] == 1

        # Cleanup
        await output_buffer.clear(worker_id)


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


class TestChatAPI:
    """Tests for chat API - testing routes/chat.py."""

    async def test_list_messages_empty(self, client: AsyncClient):
        """Test listing messages when none exist."""
        # Create project first
        project_response = await client.post(
            "/api/projects", json={"name": "Chat Test Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(f"/api/chat/projects/{project_id}/messages")
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_message(self, client: AsyncClient):
        """Test creating a chat message."""
        # Create project first
        project_response = await client.post(
            "/api/projects", json={"name": "Message Create Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            f"/api/chat/projects/{project_id}/messages",
            json={
                "project_id": project_id,
                "role": "user",
                "content": "Hello, this is a test message",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "user"
        assert data["content"] == "Hello, this is a test message"
        assert data["project_id"] == project_id

    async def test_create_message_with_task(self, client: AsyncClient):
        """Test creating a chat message associated with a task."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Message Task Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Chat Task"},
        )
        task_id = task_response.json()["id"]

        response = await client.post(
            f"/api/chat/projects/{project_id}/messages",
            json={
                "project_id": project_id,
                "task_id": task_id,
                "role": "assistant",
                "content": "I will help with this task",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == task_id

    async def test_create_message_project_mismatch(self, client: AsyncClient):
        """Test that project_id in body must match URL."""
        # Create two projects
        project1_response = await client.post(
            "/api/projects", json={"name": "Project 1"}
        )
        project1_id = project1_response.json()["id"]

        project2_response = await client.post(
            "/api/projects", json={"name": "Project 2"}
        )
        project2_id = project2_response.json()["id"]

        # Try to create message with mismatched project IDs
        response = await client.post(
            f"/api/chat/projects/{project1_id}/messages",
            json={
                "project_id": project2_id,  # Different from URL
                "role": "user",
                "content": "This should fail",
            },
        )
        assert response.status_code == 400

    async def test_list_messages_with_filter(self, client: AsyncClient):
        """Test listing messages with task filter."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Filter Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Filter Task"},
        )
        task_id = task_response.json()["id"]

        # Create messages
        await client.post(
            f"/api/chat/projects/{project_id}/messages",
            json={
                "project_id": project_id,
                "role": "user",
                "content": "Message without task",
            },
        )
        await client.post(
            f"/api/chat/projects/{project_id}/messages",
            json={
                "project_id": project_id,
                "task_id": task_id,
                "role": "user",
                "content": "Message with task",
            },
        )

        # Filter by task
        response = await client.get(
            f"/api/chat/projects/{project_id}/messages?task_id={task_id}"
        )
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 1
        assert messages[0]["content"] == "Message with task"

    async def test_get_recent_messages(self, client: AsyncClient):
        """Test getting recent messages."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Recent Messages Project"}
        )
        project_id = project_response.json()["id"]

        # Create multiple messages
        for i in range(5):
            await client.post(
                f"/api/chat/projects/{project_id}/messages",
                json={
                    "project_id": project_id,
                    "role": "user",
                    "content": f"Message {i}",
                },
            )

        # Get last 3
        response = await client.get(
            f"/api/chat/projects/{project_id}/messages/recent?count=3"
        )
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 3
        # Should be in chronological order (oldest first of the recent)
        assert messages[0]["content"] == "Message 2"
        assert messages[2]["content"] == "Message 4"

    async def test_get_message_count(self, client: AsyncClient):
        """Test getting message count."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Count Project"}
        )
        project_id = project_response.json()["id"]

        # Create messages
        for i in range(3):
            await client.post(
                f"/api/chat/projects/{project_id}/messages",
                json={
                    "project_id": project_id,
                    "role": "user",
                    "content": f"Message {i}",
                },
            )

        response = await client.get(
            f"/api/chat/projects/{project_id}/messages/count"
        )
        assert response.status_code == 200
        assert response.json()["count"] == 3

    async def test_list_summaries_empty(self, client: AsyncClient):
        """Test listing summaries when none exist."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Summary Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(f"/api/chat/projects/{project_id}/summaries")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_latest_summary_not_found(self, client: AsyncClient):
        """Test getting latest summary when none exist returns 404."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "No Summary Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(
            f"/api/chat/projects/{project_id}/summaries/latest"
        )
        assert response.status_code == 404

    async def test_get_history_context(self, client: AsyncClient):
        """Test getting history context."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Context Project"}
        )
        project_id = project_response.json()["id"]

        # Create some messages
        for i in range(5):
            await client.post(
                f"/api/chat/projects/{project_id}/messages",
                json={
                    "project_id": project_id,
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                },
            )

        response = await client.post(f"/api/chat/projects/{project_id}/context")
        assert response.status_code == 200
        data = response.json()
        assert data["total_messages"] == 5
        assert "recent_messages" in data
        assert "summaries" in data
        assert "key_decisions" in data
        assert "formatted_prompt" in data
        assert "estimated_tokens" in data

    async def test_get_history_context_with_config(self, client: AsyncClient):
        """Test getting history context with custom config."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Config Context Project"}
        )
        project_id = project_response.json()["id"]

        # Create messages
        for i in range(3):
            await client.post(
                f"/api/chat/projects/{project_id}/messages",
                json={
                    "project_id": project_id,
                    "role": "user",
                    "content": f"Message {i}",
                },
            )

        response = await client.post(
            f"/api/chat/projects/{project_id}/context",
            json={"recent_verbatim": 2},
        )
        assert response.status_code == 200
        data = response.json()
        # Should only return 2 recent messages
        assert len(data["recent_messages"]) == 2

    async def test_clear_summaries(self, client: AsyncClient):
        """Test clearing summaries."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Clear Summary Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.delete(
            f"/api/chat/projects/{project_id}/summaries?after_id=0"
        )
        assert response.status_code == 200
        assert "deleted" in response.json()


class TestFileUploadAPI:
    """Tests for file upload API."""

    async def test_upload_text_file(self, client: AsyncClient):
        """Test uploading a text file."""
        import contextlib
        import io
        from pathlib import Path

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Upload Test Project"}
        )
        project_id = project_response.json()["id"]

        # Create file content
        content = b"print('Hello, World!')"
        files = {"file": ("test.py", io.BytesIO(content), "text/x-python")}

        response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "test.py"
        assert data["size"] == len(content)
        assert data["media_type"] == "code"
        assert "path" in data

        # Clean up uploaded file
        with contextlib.suppress(FileNotFoundError):
            Path(data["path"]).unlink()

    async def test_upload_image_file(self, client: AsyncClient):
        """Test uploading an image file."""
        import contextlib
        import io
        from pathlib import Path

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Image Upload Project"}
        )
        project_id = project_response.json()["id"]

        # Minimal PNG (1x1 transparent pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
            0x42, 0x60, 0x82,
        ])
        files = {"file": ("test.png", io.BytesIO(png_data), "image/png")}

        response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "test.png"
        assert data["media_type"] == "image"
        assert data["mime_type"] == "image/png"

        # Clean up
        with contextlib.suppress(FileNotFoundError):
            Path(data["path"]).unlink()

    async def test_upload_empty_file_rejected(self, client: AsyncClient):
        """Test that empty files are rejected."""
        import io

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Empty File Project"}
        )
        project_id = project_response.json()["id"]

        files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}

        response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    async def test_upload_file_too_large_rejected(self, client: AsyncClient):
        """Test that files exceeding size limit are rejected."""
        import io

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Large File Project"}
        )
        project_id = project_response.json()["id"]

        # Create 11MB file (limit is 10MB)
        large_content = b"x" * (11 * 1024 * 1024)
        files = {"file": ("large.bin", io.BytesIO(large_content), "application/octet-stream")}

        response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    async def test_upload_creates_message_with_attachment(self, client: AsyncClient):
        """Test creating a message with an uploaded file attachment."""
        import contextlib
        import io
        from pathlib import Path

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Attachment Message Project"}
        )
        project_id = project_response.json()["id"]

        # Upload a file
        content = b"Configuration data"
        files = {"file": ("config.json", io.BytesIO(content), "application/json")}

        upload_response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert upload_response.status_code == 201
        upload_data = upload_response.json()

        # Create message with attachment
        message_response = await client.post(
            f"/api/chat/projects/{project_id}/messages",
            json={
                "project_id": project_id,
                "role": "user",
                "content": "Here's the config file",
                "media_type": upload_data["media_type"],
                "media_path": upload_data["path"],
            },
        )
        assert message_response.status_code == 201
        message_data = message_response.json()
        assert message_data["media_type"] == "code"
        assert message_data["media_path"] == upload_data["path"]

        # Clean up
        with contextlib.suppress(FileNotFoundError):
            Path(upload_data["path"]).unlink()

    async def test_get_uploaded_file_metadata(self, client: AsyncClient):
        """Test getting metadata for an uploaded file."""
        import contextlib
        import io
        from pathlib import Path

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "File Metadata Project"}
        )
        project_id = project_response.json()["id"]

        # Upload a file
        content = b"Test document content"
        files = {"file": ("doc.txt", io.BytesIO(content), "text/plain")}

        upload_response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert upload_response.status_code == 201
        upload_data = upload_response.json()

        # Extract filename from path
        filename = Path(upload_data["path"]).name

        # Get file metadata
        metadata_response = await client.get(
            f"/api/chat/projects/{project_id}/uploads/{filename}"
        )
        assert metadata_response.status_code == 200
        metadata = metadata_response.json()
        assert metadata["size"] == len(content)

        # Clean up
        with contextlib.suppress(FileNotFoundError):
            Path(upload_data["path"]).unlink()

    async def test_get_uploaded_file_not_found(self, client: AsyncClient):
        """Test getting metadata for non-existent file."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Not Found Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(
            f"/api/chat/projects/{project_id}/uploads/nonexistent.txt"
        )
        assert response.status_code == 404

    async def test_download_uploaded_file(self, client: AsyncClient):
        """Test downloading an uploaded file."""
        import contextlib
        import io
        from pathlib import Path

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Download Test Project"}
        )
        project_id = project_response.json()["id"]

        # Upload a file
        content = b"Hello, World! This is a test file."
        files = {"file": ("hello.txt", io.BytesIO(content), "text/plain")}

        upload_response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert upload_response.status_code == 201
        upload_data = upload_response.json()

        # Extract filename from path
        filename = Path(upload_data["path"]).name

        # Download the file
        download_response = await client.get(
            f"/api/chat/projects/{project_id}/uploads/{filename}/download"
        )
        assert download_response.status_code == 200
        assert download_response.content == content
        assert download_response.headers["content-type"] == "text/plain; charset=utf-8"
        # Check Content-Disposition header for original filename
        assert "hello.txt" in download_response.headers.get("content-disposition", "")

        # Clean up
        with contextlib.suppress(FileNotFoundError):
            Path(upload_data["path"]).unlink()

    async def test_download_uploaded_file_not_found(self, client: AsyncClient):
        """Test downloading a non-existent file returns 404."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Download Not Found Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(
            f"/api/chat/projects/{project_id}/uploads/nonexistent.txt/download"
        )
        assert response.status_code == 404

    async def test_download_uploaded_binary_file(self, client: AsyncClient):
        """Test downloading a binary file (image)."""
        import contextlib
        import io
        from pathlib import Path

        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Binary Download Project"}
        )
        project_id = project_response.json()["id"]

        # Minimal PNG (1x1 transparent pixel)
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
            0x42, 0x60, 0x82,
        ])
        files = {"file": ("image.png", io.BytesIO(png_data), "image/png")}

        upload_response = await client.post(
            f"/api/chat/projects/{project_id}/upload",
            files=files,
        )
        assert upload_response.status_code == 201
        upload_data = upload_response.json()

        # Extract filename from path
        filename = Path(upload_data["path"]).name

        # Download the file
        download_response = await client.get(
            f"/api/chat/projects/{project_id}/uploads/{filename}/download"
        )
        assert download_response.status_code == 200
        assert download_response.content == png_data
        assert download_response.headers["content-type"] == "image/png"
        # Check original filename in content-disposition
        assert "image.png" in download_response.headers.get("content-disposition", "")

        # Clean up
        with contextlib.suppress(FileNotFoundError):
            Path(upload_data["path"]).unlink()


class TestFileBrowserAPI:
    """Tests for file browser API."""

    async def test_list_directory_no_working_dir(self, client: AsyncClient):
        """Test listing files when project has no working directory configured."""
        # Create project without working_dir
        project_response = await client.post(
            "/api/projects", json={"name": "No WorkDir Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(f"/api/projects/{project_id}/files")
        assert response.status_code == 400
        assert "working directory" in response.json()["detail"].lower()

    async def test_list_directory_with_working_dir(self, client: AsyncClient, app_with_db):
        """Test listing files with a valid working directory."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            test_dir = Path(tmpdir)
            (test_dir / "file1.py").write_text("# Python file")
            (test_dir / "file2.txt").write_text("Text file")
            (test_dir / "subdir").mkdir()
            (test_dir / "subdir" / "nested.js").write_text("// JS file")

            # Create project with working_dir in settings
            project_response = await client.post(
                "/api/projects",
                json={
                    "name": "File Browser Project",
                    "repo_url": str(test_dir),  # Use local path
                },
            )
            project_id = project_response.json()["id"]

            # List root directory
            response = await client.get(f"/api/projects/{project_id}/files")
            assert response.status_code == 200
            data = response.json()
            assert data["path"] == ""
            assert data["parent_path"] is None
            entries = {e["name"]: e for e in data["entries"]}
            assert "file1.py" in entries
            assert "file2.txt" in entries
            assert "subdir" in entries
            assert entries["subdir"]["is_dir"] is True
            assert entries["file1.py"]["is_dir"] is False

    async def test_list_subdirectory(self, client: AsyncClient):
        """Test listing files in a subdirectory."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            (test_dir / "subdir").mkdir()
            (test_dir / "subdir" / "nested.py").write_text("# Nested")

            project_response = await client.post(
                "/api/projects",
                json={"name": "Subdir Project", "repo_url": str(test_dir)},
            )
            project_id = project_response.json()["id"]

            response = await client.get(
                f"/api/projects/{project_id}/files", params={"path": "subdir"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["path"] == "subdir"
            assert data["parent_path"] == ""
            entries = {e["name"]: e for e in data["entries"]}
            assert "nested.py" in entries

    async def test_get_file_content(self, client: AsyncClient):
        """Test getting file content."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            (test_dir / "test.py").write_text("print('hello')")

            project_response = await client.post(
                "/api/projects",
                json={"name": "Content Project", "repo_url": str(test_dir)},
            )
            project_id = project_response.json()["id"]

            response = await client.get(
                f"/api/projects/{project_id}/files/content", params={"path": "test.py"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["path"] == "test.py"
            assert data["content"] == "print('hello')"
            assert data["is_binary"] is False

    async def test_get_file_content_not_found(self, client: AsyncClient):
        """Test getting content of non-existent file."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            project_response = await client.post(
                "/api/projects",
                json={"name": "NotFound Project", "repo_url": tmpdir},
            )
            project_id = project_response.json()["id"]

            response = await client.get(
                f"/api/projects/{project_id}/files/content",
                params={"path": "nonexistent.py"},
            )
            assert response.status_code == 404

    async def test_path_traversal_blocked(self, client: AsyncClient):
        """Test that path traversal attempts are blocked."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            project_response = await client.post(
                "/api/projects",
                json={"name": "Traversal Project", "repo_url": tmpdir},
            )
            project_id = project_response.json()["id"]

            response = await client.get(
                f"/api/projects/{project_id}/files", params={"path": "../../../etc"}
            )
            assert response.status_code == 403


class TestMetricsAPI:
    """Tests for metrics API."""

    async def test_get_metrics(self, client: AsyncClient):
        """Test getting complete metrics."""
        response = await client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "timestamp" in data
        assert "task_stats" in data
        assert "worker_stats" in data
        assert "recent_events" in data
        assert "activity_24h" in data
        assert "activity_7d" in data

        # Check task_stats fields
        task_stats = data["task_stats"]
        assert "total" in task_stats
        assert "draft" in task_stats
        assert "ready" in task_stats
        assert "done" in task_stats
        assert "failed" in task_stats

        # Check worker_stats fields
        worker_stats = data["worker_stats"]
        assert "total" in worker_stats
        assert "idle" in worker_stats
        assert "busy" in worker_stats
        assert "offline" in worker_stats
        assert "total_completed" in worker_stats
        assert "total_failed" in worker_stats

        # Check activity fields
        assert "tasks_completed" in data["activity_24h"]
        assert "tasks_failed" in data["activity_24h"]
        assert "tasks_created" in data["activity_24h"]

    async def test_get_metrics_with_data(self, client: AsyncClient):
        """Test metrics after creating tasks and workers."""
        # Create a project
        project_response = await client.post(
            "/api/projects", json={"name": "Metrics Test Project"}
        )
        project_id = project_response.json()["id"]

        # Create some tasks
        for i in range(3):
            await client.post(
                "/api/tasks",
                json={"project_id": project_id, "title": f"Task {i}"},
            )

        # Create a worker
        await client.post(
            "/api/workers",
            json={
                "name": "Test Worker",
                "type": "test",
                "command": "echo",
            },
        )

        # Get metrics
        response = await client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()

        # Verify counts reflect our data
        assert data["task_stats"]["total"] >= 3
        assert data["worker_stats"]["total"] >= 1

    async def test_get_task_stats(self, client: AsyncClient):
        """Test getting task stats endpoint."""
        response = await client.get("/api/metrics/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "ready" in data
        assert "done" in data

    async def test_get_worker_metrics(self, client: AsyncClient):
        """Test getting worker metrics endpoint."""
        response = await client.get("/api/metrics/workers")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "idle" in data
        assert "busy" in data
        assert "total_completed" in data

    async def test_get_events(self, client: AsyncClient):
        """Test getting recent events."""
        response = await client.get("/api/metrics/events")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_events_with_filter(self, client: AsyncClient):
        """Test getting events with filters."""
        # Create a project and task to generate events
        project_response = await client.post(
            "/api/projects", json={"name": "Event Test Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Event Task"},
        )
        task_id = task_response.json()["id"]

        # Mark task as ready
        await client.post("/api/queue/enqueue", json={"task_id": task_id})

        # Get events filtered by entity_type
        response = await client.get(
            "/api/metrics/events", params={"entity_type": "task"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_activity(self, client: AsyncClient):
        """Test getting activity summary."""
        response = await client.get("/api/metrics/activity")
        assert response.status_code == 200
        data = response.json()
        assert "tasks_completed" in data
        assert "tasks_failed" in data
        assert "tasks_created" in data

    async def test_get_activity_custom_hours(self, client: AsyncClient):
        """Test getting activity with custom hours parameter."""
        response = await client.get("/api/metrics/activity", params={"hours": 48})
        assert response.status_code == 200
        data = response.json()
        assert "tasks_completed" in data

    async def test_get_metrics_event_limit(self, client: AsyncClient):
        """Test metrics with custom event limit."""
        response = await client.get("/api/metrics", params={"event_limit": 5})
        assert response.status_code == 200
        data = response.json()
        # Recent events should be capped at the limit
        assert len(data["recent_events"]) <= 5


class TestInputAPI:
    """Tests for input API - testing routes/input.py."""

    async def test_submit_simple_input(self, client: AsyncClient):
        """Test submitting simple input creates a task."""
        # Create project first
        project_response = await client.post(
            "/api/projects", json={"name": "Input Test Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            "/api/input",
            json={
                "project_id": project_id,
                "text": "Add a logout button to the navigation bar",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["created_tasks"]) >= 1
        assert any("logout" in t["title"].lower() or "button" in t["title"].lower()
                   for t in data["created_tasks"])

    async def test_submit_multiple_tasks_input(self, client: AsyncClient):
        """Test submitting input with multiple tasks."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Multi Input Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            "/api/input",
            json={
                "project_id": project_id,
                "text": "Fix the login bug. Then add password reset. Finally, test the authentication flow.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["created_tasks"]) >= 2

    async def test_submit_empty_input(self, client: AsyncClient):
        """Test submitting empty input."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Empty Input Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            "/api/input",
            json={
                "project_id": project_id,
                "text": "",
            },
        )
        # Should fail validation
        assert response.status_code == 422

    async def test_suggest_related(self, client: AsyncClient):
        """Test suggesting related tasks."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Suggest Related Project"}
        )
        project_id = project_response.json()["id"]

        # Create initial task
        await client.post(
            "/api/input",
            json={
                "project_id": project_id,
                "text": "Implement user authentication system",
            },
        )

        # Get suggestions
        response = await client.post(
            "/api/input/suggest-related",
            json={
                "project_id": project_id,
                "text": "user authentication",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "related_tasks" in data

    async def test_submit_with_priority(self, client: AsyncClient):
        """Test submitting input with custom priority."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Priority Input Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            "/api/input",
            json={
                "project_id": project_id,
                "text": "Fix critical security vulnerability",
                "priority": "P0",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify task was created with P0 priority
        tasks_response = await client.get(
            f"/api/tasks?project_id={project_id}"
        )
        tasks = tasks_response.json()
        assert len(tasks) > 0
        assert tasks[0]["priority"] == "P0"

    async def test_submit_without_decompose(self, client: AsyncClient):
        """Test submitting input with decomposition disabled."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "No Decompose Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.post(
            "/api/input",
            json={
                "project_id": project_id,
                "text": "Build a complete API with multiple endpoints",
                "auto_decompose": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestLogsAPI:
    """Tests for logs API."""

    async def test_create_log(self, client: AsyncClient):
        """Test creating a log entry."""
        response = await client.post(
            "/api/logs",
            json={
                "level": "info",
                "component": "api",
                "message": "Test log message",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["level"] == "info"
        assert data["component"] == "api"
        assert data["message"] == "Test log message"
        assert "id" in data
        assert "timestamp" in data

    async def test_create_log_with_context(self, client: AsyncClient):
        """Test creating a log entry with task and worker context."""
        # Create project, task, and worker
        project_response = await client.post(
            "/api/projects", json={"name": "Log Context Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Log Test Task"},
        )
        task_id = task_response.json()["id"]

        worker_response = await client.post(
            "/api/workers",
            json={"name": "Log Test Worker", "type": "test", "command": "echo"},
        )
        worker_id = worker_response.json()["id"]

        response = await client.post(
            "/api/logs",
            json={
                "level": "warning",
                "component": "scheduler",
                "message": "Task taking longer than expected",
                "task_id": task_id,
                "worker_id": worker_id,
                "project_id": project_id,
                "data": {"elapsed_seconds": 120},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == task_id
        assert data["worker_id"] == worker_id
        assert data["project_id"] == project_id
        assert data["data"]["elapsed_seconds"] == 120

    async def test_list_logs_empty(self, client: AsyncClient):
        """Test listing logs when none exist."""
        response = await client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data

    async def test_list_logs_with_data(self, client: AsyncClient):
        """Test listing logs with existing data."""
        # Create some logs
        for i in range(5):
            await client.post(
                "/api/logs",
                json={
                    "level": "info",
                    "component": "api",
                    "message": f"Test log {i}",
                },
            )

        response = await client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5
        assert len(data["logs"]) >= 5

    async def test_list_logs_filter_by_component(self, client: AsyncClient):
        """Test filtering logs by component."""
        # Create logs for different components
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "api", "message": "API log"},
        )
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "scheduler", "message": "Scheduler log"},
        )

        response = await client.get("/api/logs", params={"component": "api"})
        assert response.status_code == 200
        data = response.json()
        for log in data["logs"]:
            assert log["component"] == "api"

    async def test_list_logs_filter_by_level(self, client: AsyncClient):
        """Test filtering logs by level."""
        # Create logs with different levels
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "api", "message": "Info log"},
        )
        await client.post(
            "/api/logs",
            json={"level": "error", "component": "api", "message": "Error log"},
        )

        response = await client.get("/api/logs", params={"level": "error"})
        assert response.status_code == 200
        data = response.json()
        for log in data["logs"]:
            assert log["level"] == "error"

    async def test_list_logs_pagination(self, client: AsyncClient):
        """Test log pagination."""
        # Create 10 logs
        for i in range(10):
            await client.post(
                "/api/logs",
                json={"level": "info", "component": "api", "message": f"Paginated log {i}"},
            )

        # Get first page
        response = await client.get("/api/logs", params={"limit": 5, "offset": 0})
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 5
        assert data["offset"] == 0
        assert data["limit"] == 5

        # Get second page
        response = await client.get("/api/logs", params={"limit": 5, "offset": 5})
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 5

    async def test_list_logs_search(self, client: AsyncClient):
        """Test full-text search in logs."""
        # Create logs with different messages
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "api", "message": "Database connection established"},
        )
        await client.post(
            "/api/logs",
            json={"level": "error", "component": "api", "message": "Authentication failed"},
        )

        response = await client.get("/api/logs", params={"search": "Database"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) >= 1
        assert any("Database" in log["message"] for log in data["logs"])

    async def test_get_recent_logs(self, client: AsyncClient):
        """Test getting recent logs."""
        # Create a log
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "api", "message": "Recent log"},
        )

        response = await client.get("/api/logs/recent", params={"minutes": 60})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_logs_for_task(self, client: AsyncClient):
        """Test getting logs for a specific task."""
        # Create project and task
        project_response = await client.post(
            "/api/projects", json={"name": "Task Log Project"}
        )
        project_id = project_response.json()["id"]

        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Logged Task"},
        )
        task_id = task_response.json()["id"]

        # Create logs for this task
        await client.post(
            "/api/logs",
            json={
                "level": "info",
                "component": "worker",
                "message": "Task started",
                "task_id": task_id,
            },
        )
        await client.post(
            "/api/logs",
            json={
                "level": "info",
                "component": "worker",
                "message": "Task completed",
                "task_id": task_id,
            },
        )

        response = await client.get(f"/api/logs/for-task/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        for log in data:
            assert log["task_id"] == task_id

    async def test_get_logs_for_task_not_found(self, client: AsyncClient):
        """Test getting logs for non-existent task."""
        response = await client.get("/api/logs/for-task/bd-nonexistent")
        assert response.status_code == 404

    async def test_get_logs_for_worker(self, client: AsyncClient):
        """Test getting logs for a specific worker."""
        # Create worker
        worker_response = await client.post(
            "/api/workers",
            json={"name": "Logged Worker", "type": "test", "command": "echo"},
        )
        worker_id = worker_response.json()["id"]

        # Create logs for this worker
        await client.post(
            "/api/logs",
            json={
                "level": "info",
                "component": "scheduler",
                "message": "Worker assigned task",
                "worker_id": worker_id,
            },
        )

        response = await client.get(f"/api/logs/for-worker/{worker_id}")
        assert response.status_code == 200
        data = response.json()
        for log in data:
            assert log["worker_id"] == worker_id

    async def test_get_logs_for_worker_not_found(self, client: AsyncClient):
        """Test getting logs for non-existent worker."""
        response = await client.get("/api/logs/for-worker/worker-nonexistent")
        assert response.status_code == 404

    async def test_get_log_components(self, client: AsyncClient):
        """Test getting list of log components."""
        response = await client.get("/api/logs/components")
        assert response.status_code == 200
        data = response.json()
        assert "api" in data
        assert "scheduler" in data
        assert "worker" in data

    async def test_get_log_levels(self, client: AsyncClient):
        """Test getting list of log levels."""
        response = await client.get("/api/logs/levels")
        assert response.status_code == 200
        data = response.json()
        assert "debug" in data
        assert "info" in data
        assert "warning" in data
        assert "error" in data
        assert "critical" in data

    async def test_get_log_stats(self, client: AsyncClient):
        """Test getting log statistics."""
        # Create logs with different levels and components
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "api", "message": "Info 1"},
        )
        await client.post(
            "/api/logs",
            json={"level": "error", "component": "scheduler", "message": "Error 1"},
        )

        response = await client.get("/api/logs/stats", params={"hours": 24})
        assert response.status_code == 200
        data = response.json()
        assert "period_hours" in data
        assert "total" in data
        assert "errors" in data
        assert "by_level" in data
        assert "by_component" in data

    async def test_clear_old_logs(self, client: AsyncClient):
        """Test clearing old logs."""
        # Create a log
        await client.post(
            "/api/logs",
            json={"level": "info", "component": "api", "message": "Log to keep"},
        )

        # Try to clear logs older than 7 days (should delete nothing recent)
        response = await client.delete("/api/logs", params={"days": 7})
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data
        assert "cutoff" in data

    async def test_create_log_emits_websocket_event(self, client: AsyncClient):
        """Test that creating a log emits a WebSocket event."""
        import asyncio

        from ringmaster.events import event_bus
        from ringmaster.events.types import EventType

        # Track events received
        received_events = []

        async def capture_event(event):
            received_events.append(event)

        event_bus.add_callback(capture_event)

        try:
            # Create a log entry
            response = await client.post(
                "/api/logs",
                json={
                    "level": "info",
                    "component": "api",
                    "message": "WebSocket test log",
                    "project_id": None,
                },
            )
            assert response.status_code == 201
            log_data = response.json()

            # Allow event to be processed
            await asyncio.sleep(0.05)

            # Verify event was emitted
            log_events = [e for e in received_events if e.type == EventType.LOG_CREATED]
            assert len(log_events) >= 1

            # Check event data
            last_log_event = log_events[-1]
            assert last_log_event.data["id"] == log_data["id"]
            assert last_log_event.data["level"] == "info"
            assert last_log_event.data["component"] == "api"
            assert last_log_event.data["message"] == "WebSocket test log"

        finally:
            event_bus.remove_callback(capture_event)

    async def test_create_log_with_project_emits_event_with_project_id(
        self, client: AsyncClient
    ):
        """Test that log events include project_id for filtering."""
        import asyncio

        from ringmaster.events import event_bus
        from ringmaster.events.types import EventType

        # Create a project first
        project_response = await client.post(
            "/api/projects", json={"name": "Log Event Project"}
        )
        project_id = project_response.json()["id"]

        # Track events received
        received_events = []

        async def capture_event(event):
            received_events.append(event)

        event_bus.add_callback(capture_event)

        try:
            # Create a log entry with project_id
            response = await client.post(
                "/api/logs",
                json={
                    "level": "warning",
                    "component": "scheduler",
                    "message": "Project-scoped log",
                    "project_id": project_id,
                },
            )
            assert response.status_code == 201

            # Allow event to be processed
            await asyncio.sleep(0.05)

            # Verify event includes project_id for filtering
            log_events = [e for e in received_events if e.type == EventType.LOG_CREATED]
            assert len(log_events) >= 1

            last_log_event = log_events[-1]
            assert last_log_event.project_id == project_id

        finally:
            event_bus.remove_callback(capture_event)


class TestGraphAPI:
    """Tests for graph API - task dependency visualization."""

    async def test_get_graph_empty_project(self, client: AsyncClient):
        """Test getting graph for project with no tasks."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Empty Graph Project"}
        )
        project_id = project_response.json()["id"]

        response = await client.get(f"/api/graph?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["nodes"] == []
        assert data["edges"] == []
        assert data["stats"]["total_nodes"] == 0
        assert data["stats"]["total_edges"] == 0

    async def test_get_graph_with_tasks(self, client: AsyncClient):
        """Test getting graph for project with tasks."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Graph Test Project"}
        )
        project_id = project_response.json()["id"]

        # Create tasks
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
        await client.post(
            f"/api/tasks/{task2_id}/dependencies",
            json={"parent_id": task1_id},
        )

        response = await client.get(f"/api/graph?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()

        # Check nodes
        assert len(data["nodes"]) == 2
        node_ids = {n["id"] for n in data["nodes"]}
        assert task1_id in node_ids
        assert task2_id in node_ids

        # Check edges
        assert len(data["edges"]) == 1
        edge = data["edges"][0]
        assert edge["source"] == task1_id
        assert edge["target"] == task2_id

        # Check stats
        assert data["stats"]["total_nodes"] == 2
        assert data["stats"]["total_edges"] == 1

    async def test_get_graph_includes_node_properties(self, client: AsyncClient):
        """Test that graph nodes include necessary properties."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Node Properties Project"}
        )
        project_id = project_response.json()["id"]

        # Create task
        task_response = await client.post(
            "/api/tasks",
            json={
                "project_id": project_id,
                "title": "Test Task",
                "priority": "P1",
            },
        )
        task_id = task_response.json()["id"]

        response = await client.get(f"/api/graph?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["nodes"]) == 1
        node = data["nodes"][0]
        assert node["id"] == task_id
        assert node["title"] == "Test Task"
        assert node["task_type"] == "task"
        assert node["status"] == "draft"
        assert node["priority"] == "P1"
        assert "pagerank_score" in node
        assert "on_critical_path" in node

    async def test_get_graph_excludes_done_by_default(self, client: AsyncClient):
        """Test that completed tasks are excluded by default."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Done Exclude Project"}
        )
        project_id = project_response.json()["id"]

        # Create task and mark as done
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Done Task"},
        )
        task_id = task_response.json()["id"]

        await client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "done"},
        )

        # Create another task that's not done
        await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Active Task"},
        )

        response = await client.get(f"/api/graph?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()

        # Should only have 1 node (the active task)
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["title"] == "Active Task"

    async def test_get_graph_include_done(self, client: AsyncClient):
        """Test including completed tasks in the graph."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Include Done Project"}
        )
        project_id = project_response.json()["id"]

        # Create task and mark as done
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Done Task"},
        )
        task_id = task_response.json()["id"]

        await client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "done"},
        )

        response = await client.get(
            f"/api/graph?project_id={project_id}&include_done=true"
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["status"] == "done"

    async def test_get_graph_with_epic(self, client: AsyncClient):
        """Test graph includes epics with correct type."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Epic Graph Project"}
        )
        project_id = project_response.json()["id"]

        # Create epic
        await client.post(
            "/api/tasks/epics",
            json={
                "project_id": project_id,
                "title": "Test Epic",
                "acceptance_criteria": ["Criterion 1"],
            },
        )

        response = await client.get(f"/api/graph?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["task_type"] == "epic"

    async def test_get_graph_exclude_subtasks(self, client: AsyncClient):
        """Test excluding subtasks from the graph."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Subtask Exclude Project"}
        )
        project_id = project_response.json()["id"]

        # Create parent task
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Parent Task"},
        )
        task_id = task_response.json()["id"]

        # Create subtask
        await client.post(
            "/api/tasks",
            json={
                "project_id": project_id,
                "title": "Subtask",
                "parent_id": task_id,
                "task_type": "subtask",
            },
        )

        response = await client.get(
            f"/api/graph?project_id={project_id}&include_subtasks=false"
        )
        assert response.status_code == 200
        data = response.json()

        # Should only have parent task
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["title"] == "Parent Task"

    async def test_get_graph_stats_by_status(self, client: AsyncClient):
        """Test that graph stats include counts by status."""
        # Create project
        project_response = await client.post(
            "/api/projects", json={"name": "Stats Status Project"}
        )
        project_id = project_response.json()["id"]

        # Create tasks with different statuses
        await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Draft Task"},
        )

        task2_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Ready Task"},
        )
        await client.post(
            "/api/queue/enqueue",
            json={"task_id": task2_response.json()["id"]},
        )

        response = await client.get(f"/api/graph?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["stats"]["total_nodes"] == 2
        assert data["stats"]["status_draft"] >= 1 or data["stats"]["status_ready"] >= 1


class TestUndoAPI:
    """Tests for undo/redo API."""

    async def test_get_history_empty(self, client: AsyncClient):
        """Test getting history when no actions exist."""
        response = await client.get("/api/undo/history")
        assert response.status_code == 200
        data = response.json()
        assert data["actions"] == []
        assert data["can_undo"] is False
        assert data["can_redo"] is False

    async def test_get_last_undoable_empty(self, client: AsyncClient):
        """Test getting last undoable when nothing to undo."""
        response = await client.get("/api/undo/last")
        assert response.status_code == 200
        assert response.json() is None

    async def test_undo_nothing(self, client: AsyncClient):
        """Test undo when nothing to undo."""
        response = await client.post("/api/undo")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Nothing to undo"

    async def test_redo_nothing(self, client: AsyncClient):
        """Test redo when nothing to redo."""
        response = await client.post("/api/undo/redo")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Nothing to redo"

    async def test_record_and_undo_task_create(self, client: AsyncClient, app_with_db):
        """Test recording a task creation action and undoing it."""
        from ringmaster.db.repositories import ActionRepository
        from ringmaster.domain import Action, ActionType, EntityType

        app, db = app_with_db

        # Create a project first
        project_response = await client.post(
            "/api/projects", json={"name": "Undo Test Project"}
        )
        project_id = project_response.json()["id"]

        # Create a task
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task to Undo"},
        )
        task_id = task_response.json()["id"]

        # Manually record the action (in real usage, the task API would do this)
        action_repo = ActionRepository(db)
        action = Action(
            action_type=ActionType.TASK_CREATED,
            entity_type=EntityType.TASK,
            entity_id=task_id,
            previous_state=None,
            new_state={
                "id": task_id,
                "project_id": project_id,
                "title": "Task to Undo",
                "type": "task",
                "priority": "P2",
                "status": "draft",
            },
            project_id=project_id,
        )
        await action_repo.record(action)

        # Verify action is in history
        response = await client.get("/api/undo/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data["actions"]) == 1
        assert data["can_undo"] is True
        assert data["actions"][0]["action_type"] == "task_created"

        # Undo the task creation
        response = await client.post("/api/undo")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Undone: Task created"

        # Verify task is deleted
        response = await client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 404

        # Verify history shows action is undone
        response = await client.get("/api/undo/history?include_undone=true")
        data = response.json()
        assert data["actions"][0]["undone"] is True

    async def test_undo_and_redo_task_update(self, client: AsyncClient, app_with_db):
        """Test undoing and redoing a task status update."""
        from ringmaster.db.repositories import ActionRepository
        from ringmaster.domain import Action, ActionType, EntityType

        app, db = app_with_db

        # Create a project
        project_response = await client.post(
            "/api/projects", json={"name": "Undo Update Project"}
        )
        project_id = project_response.json()["id"]

        # Create a task
        task_response = await client.post(
            "/api/tasks",
            json={"project_id": project_id, "title": "Task for Status Change"},
        )
        task_id = task_response.json()["id"]

        # Change task status to ready
        await client.post("/api/queue/enqueue", json={"task_id": task_id})

        # Record the status change action
        action_repo = ActionRepository(db)
        action = Action(
            action_type=ActionType.TASK_STATUS_CHANGED,
            entity_type=EntityType.TASK,
            entity_id=task_id,
            previous_state={"status": "draft"},
            new_state={"status": "ready"},
            project_id=project_id,
        )
        await action_repo.record(action)

        # Undo the status change
        response = await client.post("/api/undo")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify task is back to draft
        response = await client.get(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "draft"

        # Now redo the change
        response = await client.post("/api/undo/redo")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify task is ready again
        response = await client.get(f"/api/tasks/{task_id}")
        assert response.json()["status"] == "ready"

    async def test_history_filtered_by_project(self, client: AsyncClient, app_with_db):
        """Test that history can be filtered by project."""
        from ringmaster.db.repositories import ActionRepository
        from ringmaster.domain import Action, ActionType, EntityType

        app, db = app_with_db

        # Create two projects
        project1_response = await client.post(
            "/api/projects", json={"name": "Project 1"}
        )
        project1_id = project1_response.json()["id"]

        project2_response = await client.post(
            "/api/projects", json={"name": "Project 2"}
        )
        project2_id = project2_response.json()["id"]

        # Record actions for both projects
        action_repo = ActionRepository(db)

        action1 = Action(
            action_type=ActionType.TASK_CREATED,
            entity_type=EntityType.TASK,
            entity_id="task-1",
            new_state={"id": "task-1", "project_id": project1_id, "title": "Task 1", "type": "task"},
            project_id=project1_id,
        )
        await action_repo.record(action1)

        action2 = Action(
            action_type=ActionType.TASK_CREATED,
            entity_type=EntityType.TASK,
            entity_id="task-2",
            new_state={"id": "task-2", "project_id": project2_id, "title": "Task 2", "type": "task"},
            project_id=project2_id,
        )
        await action_repo.record(action2)

        # Get history for project 1 only
        response = await client.get(f"/api/undo/history?project_id={project1_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["actions"]) == 1
        assert data["actions"][0]["entity_id"] == "task-1"

        # Get history for project 2 only
        response = await client.get(f"/api/undo/history?project_id={project2_id}")
        data = response.json()
        assert len(data["actions"]) == 1
        assert data["actions"][0]["entity_id"] == "task-2"

        # Get all history (no project filter)
        response = await client.get("/api/undo/history")
        data = response.json()
        assert len(data["actions"]) == 2


class TestDecisionsAPI:
    """Tests for the decisions API."""

    async def _create_project_and_task(self, client: AsyncClient):
        """Helper to create a project and task for decision tests."""
        # Create project
        response = await client.post(
            "/api/projects",
            json={"name": "Decision Test Project"},
        )
        project_id = response.json()["id"]

        # Create task
        response = await client.post(
            "/api/tasks",
            json={
                "project_id": project_id,
                "title": "Test Task",
                "description": "A task that may need decisions",
            },
        )
        task_id = response.json()["id"]

        return project_id, task_id

    async def test_create_decision(self, client: AsyncClient):
        """Test creating a decision that blocks a task."""
        project_id, task_id = await self._create_project_and_task(client)

        response = await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Should we use PostgreSQL or MySQL?",
                "context": "Database selection needed",
                "options": ["PostgreSQL", "MySQL", "SQLite"],
                "recommendation": "PostgreSQL",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["question"] == "Should we use PostgreSQL or MySQL?"
        assert data["blocks_id"] == task_id
        assert data["options"] == ["PostgreSQL", "MySQL", "SQLite"]
        assert data["recommendation"] == "PostgreSQL"
        assert data["resolution"] is None

        # Verify task is now blocked
        task_response = await client.get(f"/api/tasks/{task_id}")
        assert task_response.json()["status"] == "blocked"

    async def test_list_decisions(self, client: AsyncClient):
        """Test listing decisions with filters."""
        project_id, task_id = await self._create_project_and_task(client)

        # Create two decisions
        await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Decision 1?",
                "options": ["A", "B"],
            },
        )
        await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Decision 2?",
                "options": ["X", "Y"],
            },
        )

        # List all pending decisions
        response = await client.get(f"/api/decisions?project_id={project_id}")
        assert response.status_code == 200
        decisions = response.json()
        assert len(decisions) == 2

        # List by blocks_id
        response = await client.get(f"/api/decisions?blocks_id={task_id}")
        assert len(response.json()) == 2

    async def test_get_decision(self, client: AsyncClient):
        """Test getting a specific decision."""
        project_id, task_id = await self._create_project_and_task(client)

        create_response = await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Which framework?",
                "options": ["FastAPI", "Flask"],
            },
        )
        decision_id = create_response.json()["id"]

        response = await client.get(f"/api/decisions/{decision_id}")
        assert response.status_code == 200
        assert response.json()["question"] == "Which framework?"

    async def test_resolve_decision(self, client: AsyncClient):
        """Test resolving a decision."""
        project_id, task_id = await self._create_project_and_task(client)

        create_response = await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Deploy to cloud?",
                "options": ["AWS", "GCP", "Azure"],
            },
        )
        decision_id = create_response.json()["id"]

        # Resolve the decision
        response = await client.post(
            f"/api/decisions/{decision_id}/resolve",
            json={"resolution": "AWS"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resolution"] == "AWS"
        assert data["resolved_at"] is not None

        # Verify task is unblocked
        task_response = await client.get(f"/api/tasks/{task_id}")
        assert task_response.json()["status"] == "ready"

    async def test_resolve_already_resolved_decision(self, client: AsyncClient):
        """Test that resolving an already resolved decision fails."""
        project_id, task_id = await self._create_project_and_task(client)

        create_response = await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Deploy to cloud?",
                "options": ["AWS", "GCP"],
            },
        )
        decision_id = create_response.json()["id"]

        # Resolve first time
        await client.post(
            f"/api/decisions/{decision_id}/resolve",
            json={"resolution": "AWS"},
        )

        # Try to resolve again
        response = await client.post(
            f"/api/decisions/{decision_id}/resolve",
            json={"resolution": "GCP"},
        )
        assert response.status_code == 400
        assert "already resolved" in response.json()["detail"]

    async def test_get_decisions_for_task(self, client: AsyncClient):
        """Test getting decisions blocking a specific task."""
        project_id, task_id = await self._create_project_and_task(client)

        await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Decision A?",
            },
        )

        response = await client.get(f"/api/decisions/for-task/{task_id}")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    async def test_decision_stats(self, client: AsyncClient):
        """Test getting decision statistics."""
        project_id, task_id = await self._create_project_and_task(client)

        # Create and resolve one decision
        create_response = await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Resolved decision?",
            },
        )
        await client.post(
            f"/api/decisions/{create_response.json()['id']}/resolve",
            json={"resolution": "Yes"},
        )

        # Create another pending decision
        await client.post(
            "/api/decisions",
            json={
                "project_id": project_id,
                "blocks_id": task_id,
                "question": "Pending decision?",
            },
        )

        response = await client.get(f"/api/projects/{project_id}/decisions/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total"] == 2
        assert stats["resolved"] == 1
        assert stats["pending"] == 1


class TestQuestionsAPI:
    """Tests for the questions API."""

    async def _create_project_and_task(self, client: AsyncClient):
        """Helper to create a project and task for question tests."""
        # Create project
        response = await client.post(
            "/api/projects",
            json={"name": "Question Test Project"},
        )
        project_id = response.json()["id"]

        # Create task
        response = await client.post(
            "/api/tasks",
            json={
                "project_id": project_id,
                "title": "Test Task",
                "description": "A task with questions",
            },
        )
        task_id = response.json()["id"]

        return project_id, task_id

    async def test_create_question(self, client: AsyncClient):
        """Test creating a question."""
        project_id, task_id = await self._create_project_and_task(client)

        response = await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "What is the expected date format?",
                "urgency": "high",
                "default_answer": "ISO 8601",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["question"] == "What is the expected date format?"
        assert data["related_id"] == task_id
        assert data["urgency"] == "high"
        assert data["default_answer"] == "ISO 8601"
        assert data["answer"] is None

    async def test_list_questions(self, client: AsyncClient):
        """Test listing questions with filters."""
        project_id, task_id = await self._create_project_and_task(client)

        # Create questions with different urgency
        await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "High urgency question?",
                "urgency": "high",
            },
        )
        await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "Low urgency question?",
                "urgency": "low",
            },
        )

        response = await client.get(f"/api/questions?project_id={project_id}")
        assert response.status_code == 200
        questions = response.json()
        assert len(questions) == 2
        # High urgency should come first
        assert questions[0]["urgency"] == "high"

    async def test_get_question(self, client: AsyncClient):
        """Test getting a specific question."""
        project_id, task_id = await self._create_project_and_task(client)

        create_response = await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "What encoding to use?",
            },
        )
        question_id = create_response.json()["id"]

        response = await client.get(f"/api/questions/{question_id}")
        assert response.status_code == 200
        assert response.json()["question"] == "What encoding to use?"

    async def test_answer_question(self, client: AsyncClient):
        """Test answering a question."""
        project_id, task_id = await self._create_project_and_task(client)

        create_response = await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "Max file size limit?",
            },
        )
        question_id = create_response.json()["id"]

        # Answer the question
        response = await client.post(
            f"/api/questions/{question_id}/answer",
            json={"answer": "10MB"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "10MB"
        assert data["answered_at"] is not None

    async def test_answer_already_answered_question(self, client: AsyncClient):
        """Test that answering an already answered question fails."""
        project_id, task_id = await self._create_project_and_task(client)

        create_response = await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "Max connections?",
            },
        )
        question_id = create_response.json()["id"]

        # Answer first time
        await client.post(
            f"/api/questions/{question_id}/answer",
            json={"answer": "100"},
        )

        # Try to answer again
        response = await client.post(
            f"/api/questions/{question_id}/answer",
            json={"answer": "200"},
        )
        assert response.status_code == 400
        assert "already answered" in response.json()["detail"]

    async def test_get_questions_for_task(self, client: AsyncClient):
        """Test getting questions related to a specific task."""
        project_id, task_id = await self._create_project_and_task(client)

        await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "Question A?",
            },
        )

        response = await client.get(f"/api/questions/for-task/{task_id}")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    async def test_question_stats(self, client: AsyncClient):
        """Test getting question statistics."""
        project_id, task_id = await self._create_project_and_task(client)

        # Create and answer one question
        create_response = await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "Answered question?",
                "urgency": "low",
            },
        )
        await client.post(
            f"/api/questions/{create_response.json()['id']}/answer",
            json={"answer": "Yes"},
        )

        # Create pending questions with different urgency
        await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "High pending?",
                "urgency": "high",
            },
        )
        await client.post(
            "/api/questions",
            json={
                "project_id": project_id,
                "related_id": task_id,
                "question": "Medium pending?",
                "urgency": "medium",
            },
        )

        response = await client.get(f"/api/projects/{project_id}/questions/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total"] == 3
        assert stats["answered"] == 1
        assert stats["pending"] == 2
        assert stats["by_urgency"]["high"] == 1
        assert stats["by_urgency"]["medium"] == 1
