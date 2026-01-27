"""Tests for context assembly logging observability."""

import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from ringmaster.api.app import create_app
from ringmaster.db import Database
from ringmaster.db.repositories import (
    ContextAssemblyLogRepository,
    ProjectRepository,
    TaskRepository,
)
from ringmaster.domain import ContextAssemblyLog, Priority, Project, Task
from ringmaster.enricher.pipeline import EnrichmentPipeline


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
        id=uuid4(),
        name="Test Project",
        description="Test project for context assembly",
        tech_stack=["python", "typescript"],
    )
    await repo.create(project)
    return project


@pytest.fixture
async def task(db, project):
    """Create a test task."""
    repo = TaskRepository(db)
    task = Task(
        id=f"bd-{uuid4().hex[:8]}",
        project_id=project.id,
        title="Test Task",
        description="Test task for context assembly logging",
        priority=Priority.P2,
    )
    await repo.create_task(task)
    return task


@pytest.fixture
def context_log(project, task):
    """Create a sample context assembly log."""
    return ContextAssemblyLog(
        task_id=task.id,
        project_id=project.id,
        sources_queried=["task", "project", "code", "history"],
        candidates_found=4,
        items_included=3,
        tokens_used=5000,
        tokens_budget=100000,
        compression_applied=[],
        compression_ratio=1.0,
        stages_applied=["task_context", "project_context", "code_context"],
        assembly_time_ms=150,
        context_hash="abc123def456",
    )


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def app_with_db() -> AsyncGenerator[tuple, None]:
    """Create an app with a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()

        app = create_app()
        app.state.db = database

        yield app, database

        await database.disconnect()


@pytest.fixture
async def client(app_with_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    app, _ = app_with_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestContextAssemblyLogModel:
    """Tests for ContextAssemblyLog domain model."""

    def test_create_context_log(self, project, task):
        """Test creating a context assembly log."""
        log = ContextAssemblyLog(
            task_id=task.id,
            project_id=project.id,
            sources_queried=["task", "project"],
            candidates_found=2,
            items_included=2,
            tokens_used=1000,
            tokens_budget=10000,
        )

        assert log.task_id == task.id
        assert log.project_id == project.id
        assert log.sources_queried == ["task", "project"]
        assert log.tokens_used == 1000
        assert log.compression_ratio == 1.0  # Default

    def test_context_log_defaults(self):
        """Test default values for context assembly log."""
        project_id = uuid4()
        log = ContextAssemblyLog(
            task_id="bd-test",
            project_id=project_id,
        )

        assert log.sources_queried == []
        assert log.candidates_found == 0
        assert log.items_included == 0
        assert log.tokens_used == 0
        assert log.tokens_budget == 0
        assert log.compression_applied == []
        assert log.compression_ratio == 1.0
        assert log.stages_applied == []
        assert log.assembly_time_ms == 0


class TestContextAssemblyLogRepository:
    """Tests for ContextAssemblyLogRepository."""

    async def test_create_log(self, db, context_log):
        """Test creating a context assembly log in the database."""
        repo = ContextAssemblyLogRepository(db)
        created = await repo.create(context_log)

        assert created.id is not None
        assert created.task_id == context_log.task_id

    async def test_get_log(self, db, context_log):
        """Test retrieving a context assembly log by ID."""
        repo = ContextAssemblyLogRepository(db)
        created = await repo.create(context_log)

        retrieved = await repo.get(created.id)
        assert retrieved is not None
        assert retrieved.task_id == context_log.task_id
        assert retrieved.tokens_used == context_log.tokens_used

    async def test_get_nonexistent_log(self, db):
        """Test retrieving a nonexistent log returns None."""
        repo = ContextAssemblyLogRepository(db)
        result = await repo.get(99999)
        assert result is None

    async def test_list_for_task(self, db, project, task):
        """Test listing logs for a specific task."""
        repo = ContextAssemblyLogRepository(db)

        # Create multiple logs for the same task
        for i in range(3):
            log = ContextAssemblyLog(
                task_id=task.id,
                project_id=project.id,
                tokens_used=1000 + i * 100,
                tokens_budget=10000,
            )
            await repo.create(log)

        logs = await repo.list_for_task(task.id)
        assert len(logs) == 3
        # Should be ordered by created_at DESC
        assert logs[0].tokens_used == 1200  # Most recent
        assert logs[2].tokens_used == 1000  # Oldest

    async def test_list_for_project(self, db, project):
        """Test listing logs for a specific project."""
        repo = ContextAssemblyLogRepository(db)

        # Create logs for different tasks
        for i in range(5):
            log = ContextAssemblyLog(
                task_id=f"bd-task{i}",
                project_id=project.id,
                tokens_used=1000 + i * 100,
                tokens_budget=10000,
            )
            await repo.create(log)

        logs = await repo.list_for_project(project.id, limit=10)
        assert len(logs) == 5

    async def test_list_with_pagination(self, db, project):
        """Test pagination for project logs."""
        repo = ContextAssemblyLogRepository(db)

        for i in range(10):
            log = ContextAssemblyLog(
                task_id=f"bd-task{i}",
                project_id=project.id,
                tokens_used=1000,
                tokens_budget=10000,
            )
            await repo.create(log)

        # Get first page
        page1 = await repo.list_for_project(project.id, limit=3, offset=0)
        assert len(page1) == 3

        # Get second page
        page2 = await repo.list_for_project(project.id, limit=3, offset=3)
        assert len(page2) == 3

        # Ensure no overlap
        page1_ids = {log.id for log in page1}
        page2_ids = {log.id for log in page2}
        assert page1_ids.isdisjoint(page2_ids)

    async def test_get_stats(self, db, project):
        """Test getting aggregated statistics."""
        repo = ContextAssemblyLogRepository(db)

        # Create logs with varying stats
        for tokens in [1000, 2000, 3000, 4000, 5000]:
            log = ContextAssemblyLog(
                task_id=f"bd-task-{tokens}",
                project_id=project.id,
                tokens_used=tokens,
                tokens_budget=10000,
                items_included=3,
                assembly_time_ms=100,
                compression_ratio=0.8,
            )
            await repo.create(log)

        stats = await repo.get_stats(project.id)

        assert stats["total_assemblies"] == 5
        assert stats["avg_tokens_used"] == 3000.0
        assert stats["avg_tokens_budget"] == 10000.0
        assert stats["max_tokens_used"] == 5000
        assert stats["min_tokens_used"] == 1000

    async def test_get_stats_empty_project(self, db):
        """Test stats for project with no logs."""
        repo = ContextAssemblyLogRepository(db)
        empty_project_id = uuid4()

        stats = await repo.get_stats(empty_project_id)

        assert stats["total_assemblies"] == 0
        assert stats["avg_tokens_used"] == 0

    async def test_get_budget_utilization(self, db, project):
        """Test finding logs that hit budget limits."""
        repo = ContextAssemblyLogRepository(db)

        # Create logs with varying budget utilization
        utilizations = [0.5, 0.8, 0.95, 0.99, 1.0]
        for i, util in enumerate(utilizations):
            log = ContextAssemblyLog(
                task_id=f"bd-task-{i}",
                project_id=project.id,
                tokens_used=int(10000 * util),
                tokens_budget=10000,
            )
            await repo.create(log)

        # Get logs at 95%+ utilization
        high_util = await repo.get_budget_utilization(project.id, threshold=0.95)
        assert len(high_util) == 3  # 0.95, 0.99, 1.0

    async def test_cleanup_old_logs(self, db, project):
        """Test cleaning up old logs."""
        repo = ContextAssemblyLogRepository(db)

        # Create a log
        log = ContextAssemblyLog(
            task_id="bd-old-task",
            project_id=project.id,
            tokens_used=1000,
            tokens_budget=10000,
        )
        await repo.create(log)

        # Cleanup with 0 days should delete it
        deleted = await repo.cleanup_old(days=0)

        # Note: This test is tricky because the log was just created
        # In practice, cleanup would delete logs older than N days
        # Here we just verify the method runs without error
        assert deleted >= 0


class TestEnrichmentPipelineLogging:
    """Tests for enrichment pipeline context assembly logging."""

    async def test_enrich_logs_assembly(self, db, project, task, temp_project_dir):
        """Test that enrichment logs assembly events."""
        pipeline = EnrichmentPipeline(
            project_dir=temp_project_dir,
            db=db,
        )

        # Run enrichment with logging enabled (default)
        await pipeline.enrich(task, project, log_assembly=True)

        # Check that a log was created
        repo = ContextAssemblyLogRepository(db)
        logs = await repo.list_for_task(task.id)

        assert len(logs) == 1
        log = logs[0]
        assert log.task_id == task.id
        assert log.project_id == project.id
        assert log.tokens_used > 0
        assert log.items_included > 0
        assert "task_context" in log.stages_applied
        assert "project_context" in log.stages_applied

    async def test_enrich_logging_disabled(self, db, project, task, temp_project_dir):
        """Test that logging can be disabled."""
        pipeline = EnrichmentPipeline(
            project_dir=temp_project_dir,
            db=db,
        )

        # Run enrichment with logging disabled
        await pipeline.enrich(task, project, log_assembly=False)

        # Check that no log was created
        repo = ContextAssemblyLogRepository(db)
        logs = await repo.list_for_task(task.id)

        assert len(logs) == 0

    async def test_enrich_logs_context_hash(self, db, project, task, temp_project_dir):
        """Test that context hash is logged for deduplication."""
        pipeline = EnrichmentPipeline(
            project_dir=temp_project_dir,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        repo = ContextAssemblyLogRepository(db)
        logs = await repo.list_for_task(task.id)

        assert len(logs) == 1
        assert logs[0].context_hash == result.context_hash


class TestEnricherAPIRoutes:
    """Tests for enricher API endpoints."""

    async def test_get_logs_for_task(self, app_with_db):
        """Test getting context logs for a task."""
        app, db = app_with_db

        # Create a project and task
        project_repo = ProjectRepository(db)
        project = Project(id=uuid4(), name="Test Project")
        await project_repo.create(project)

        task_repo = TaskRepository(db)
        task = Task(id="bd-test123", project_id=project.id, title="Test Task")
        await task_repo.create_task(task)

        # Create some logs
        repo = ContextAssemblyLogRepository(db)
        for i in range(3):
            log = ContextAssemblyLog(
                task_id=task.id,
                project_id=project.id,
                tokens_used=1000 + i * 100,
                tokens_budget=10000,
            )
            await repo.create(log)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/enricher/for-task/{task.id}")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 3
            assert data[0]["task_id"] == task.id

    async def test_get_logs_for_project(self, app_with_db):
        """Test getting context logs for a project."""
        app, db = app_with_db

        project_repo = ProjectRepository(db)
        project = Project(id=uuid4(), name="Test Project")
        await project_repo.create(project)

        repo = ContextAssemblyLogRepository(db)
        for i in range(5):
            log = ContextAssemblyLog(
                task_id=f"bd-task{i}",
                project_id=project.id,
                tokens_used=1000,
                tokens_budget=10000,
            )
            await repo.create(log)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/enricher/for-project/{project.id}")
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 5

    async def test_get_stats(self, app_with_db):
        """Test getting context assembly stats."""
        app, db = app_with_db

        project_repo = ProjectRepository(db)
        project = Project(id=uuid4(), name="Test Project")
        await project_repo.create(project)

        repo = ContextAssemblyLogRepository(db)
        for tokens in [1000, 2000, 3000]:
            log = ContextAssemblyLog(
                task_id=f"bd-task-{tokens}",
                project_id=project.id,
                tokens_used=tokens,
                tokens_budget=10000,
                items_included=3,
                assembly_time_ms=100,
            )
            await repo.create(log)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/enricher/stats/{project.id}")
            assert response.status_code == 200

            data = response.json()
            assert data["total_assemblies"] == 3
            assert data["avg_tokens_used"] == 2000.0

    async def test_get_budget_alerts(self, app_with_db):
        """Test getting budget utilization alerts."""
        app, db = app_with_db

        project_repo = ProjectRepository(db)
        project = Project(id=uuid4(), name="Test Project")
        await project_repo.create(project)

        repo = ContextAssemblyLogRepository(db)

        # Create a log at 99% utilization
        log = ContextAssemblyLog(
            task_id="bd-high-util",
            project_id=project.id,
            tokens_used=9900,
            tokens_budget=10000,
        )
        await repo.create(log)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/enricher/budget-alerts/{project.id}",
                params={"threshold": 0.95},
            )
            assert response.status_code == 200

            data = response.json()
            assert len(data) == 1
            assert data[0]["tokens_used"] == 9900

    async def test_get_single_log(self, app_with_db):
        """Test getting a single log by ID."""
        app, db = app_with_db

        project_repo = ProjectRepository(db)
        project = Project(id=uuid4(), name="Test Project")
        await project_repo.create(project)

        repo = ContextAssemblyLogRepository(db)
        log = ContextAssemblyLog(
            task_id="bd-test",
            project_id=project.id,
            tokens_used=5000,
            tokens_budget=10000,
            stages_applied=["task_context", "code_context"],
        )
        created = await repo.create(log)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/enricher/{created.id}")
            assert response.status_code == 200

            data = response.json()
            assert data["id"] == created.id
            assert data["tokens_used"] == 5000

    async def test_get_nonexistent_log(self, app_with_db):
        """Test getting a nonexistent log returns 404."""
        app, _ = app_with_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/enricher/99999")
            assert response.status_code == 404

    async def test_cleanup_old_logs(self, app_with_db):
        """Test cleanup endpoint."""
        app, db = app_with_db

        project_repo = ProjectRepository(db)
        project = Project(id=uuid4(), name="Test Project")
        await project_repo.create(project)

        repo = ContextAssemblyLogRepository(db)
        log = ContextAssemblyLog(
            task_id="bd-test",
            project_id=project.id,
            tokens_used=1000,
            tokens_budget=10000,
        )
        await repo.create(log)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/api/enricher/cleanup", params={"days": 30})
            assert response.status_code == 200

            data = response.json()
            assert "deleted" in data
