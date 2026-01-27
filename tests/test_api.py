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
