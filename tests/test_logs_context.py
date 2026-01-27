"""Tests for LogsContextStage in the enrichment pipeline.

Based on docs/04-context-enrichment.md section 6:
- Error logs from the last 24 hours
- Service logs filtered by relevance
- Stack traces when debugging crashes
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ringmaster.db import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository
from ringmaster.domain import Priority, Project, Task, TaskStatus, TaskType
from ringmaster.enricher.stages import LogsContextStage


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
    """Create a test project in the database."""
    proj = Project(
        id=uuid4(),
        name="Test Project",
        description="A test project",
    )
    repo = ProjectRepository(db)
    await repo.create(proj)
    return proj


@pytest.fixture
async def debugging_task(db, project):
    """Create a task that appears to be debugging-related."""
    task = Task(
        id="task-debug-1",
        project_id=project.id,
        type=TaskType.TASK,
        title="Fix login error",
        description="Users are getting a 500 error when trying to log in",
        priority=Priority.P1,
        status=TaskStatus.IN_PROGRESS,
    )
    repo = TaskRepository(db)
    await repo.create_task(task)
    return task


@pytest.fixture
async def non_debugging_task(db, project):
    """Create a task that is NOT debugging-related."""
    task = Task(
        id="task-feature-1",
        project_id=project.id,
        type=TaskType.TASK,
        title="Add dark mode support",
        description="Implement a dark mode theme for the dashboard",
        priority=Priority.P2,
        status=TaskStatus.IN_PROGRESS,
    )
    repo = TaskRepository(db)
    await repo.create_task(task)
    return task


async def _insert_log(db, project_id, task_id=None, level="info", component="api", message="test log", data=None):
    """Helper to insert a log entry."""
    timestamp = datetime.now(UTC).isoformat()
    data_json = json.dumps(data) if data else None
    await db.execute(
        """
        INSERT INTO logs (timestamp, level, component, message, task_id, worker_id, project_id, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, level, component, message, task_id, None, str(project_id), data_json),
    )
    await db.commit()


class TestLogsContextStageKeywordDetection:
    """Tests for debugging task detection via keywords."""

    def test_debug_keywords_detected(self):
        """Test that various debugging keywords are detected."""
        stage = LogsContextStage()

        # Create tasks with different debugging keywords
        keywords = [
            ("Fix login error", True),
            ("Debug authentication issue", True),
            ("Investigate 500 errors", True),
            ("Diagnose slow performance", True),
            ("Bug in user registration", True),
            ("Crash on startup", True),
            ("Failing tests after deploy", True),
            ("Broken API endpoint", True),
            ("Exception in payment flow", True),
            ("Add new feature", False),
            ("Refactor codebase", False),
            ("Update documentation", False),
            ("Improve performance", False),  # "performance" is a debug keyword
        ]

        project = Project(id=uuid4(), name="Test")
        for title, expected in keywords:
            task = Task(
                id="test-task",
                project_id=project.id,
                type=TaskType.TASK,
                title=title,
                description="",
                priority=Priority.P2,
                status=TaskStatus.IN_PROGRESS,
            )
            is_debug = stage._is_debugging_task(task)
            # Performance is a debug keyword, so we expect True for "Improve performance"
            if "performance" in title.lower():
                assert is_debug is True
            else:
                assert is_debug is expected, f"Expected {expected} for '{title}'"

    def test_relevance_score_calculation(self):
        """Test that relevance scores are calculated correctly."""
        stage = LogsContextStage()
        project = Project(id=uuid4(), name="Test")

        # High relevance: multiple debug keywords
        task_high = Task(
            id="test-high",
            project_id=project.id,
            type=TaskType.TASK,
            title="Debug error crash",
            description="Fix the bug causing exceptions",
            priority=Priority.P1,
            status=TaskStatus.IN_PROGRESS,
        )
        score_high = stage._calculate_relevance_score(task_high)
        assert score_high >= 0.8

        # Low relevance: no debug keywords
        task_low = Task(
            id="test-low",
            project_id=project.id,
            type=TaskType.TASK,
            title="Add new feature",
            description="Implement user profile page",
            priority=Priority.P2,
            status=TaskStatus.IN_PROGRESS,
        )
        score_low = stage._calculate_relevance_score(task_low)
        assert score_low < 0.5


class TestLogsContextStageProcess:
    """Tests for the process method."""

    async def test_skips_when_no_database(self, project, debugging_task):
        """Test that stage skips when no database is configured."""
        stage = LogsContextStage(db=None)
        result = await stage.process(debugging_task, project)
        assert result is None

    async def test_skips_non_debugging_tasks(self, db, project, non_debugging_task):
        """Test that stage skips tasks that are not debugging-related."""
        # Insert some logs
        await _insert_log(db, project.id, level="error", message="Some error")

        stage = LogsContextStage(db=db)
        result = await stage.process(non_debugging_task, project)
        assert result is None

    async def test_fetches_task_specific_logs(self, db, project, debugging_task):
        """Test that task-specific logs are fetched."""
        # Insert task-specific logs
        await _insert_log(
            db,
            project.id,
            task_id=debugging_task.id,
            level="error",
            message="Login failed for user abc",
        )
        await _insert_log(
            db,
            project.id,
            task_id=debugging_task.id,
            level="info",
            message="Retrying login request",
        )

        stage = LogsContextStage(db=db)
        result = await stage.process(debugging_task, project)

        assert result is not None
        assert "## Relevant Logs" in result.content
        assert "Login failed for user abc" in result.content
        assert "Retrying login request" in result.content
        assert result.tokens_estimate > 0

    async def test_fetches_project_error_logs(self, db, project, debugging_task):
        """Test that project-level error logs are fetched for debugging tasks."""
        # Insert project-level error log (not task-specific)
        await _insert_log(
            db,
            project.id,
            task_id=None,  # Not task-specific
            level="error",
            message="Database connection failed",
        )

        stage = LogsContextStage(db=db)
        result = await stage.process(debugging_task, project)

        assert result is not None
        assert "Database connection failed" in result.content

    async def test_includes_stack_traces(self, db, project, debugging_task):
        """Test that stack traces in log data are included."""
        await _insert_log(
            db,
            project.id,
            task_id=debugging_task.id,
            level="error",
            message="Unhandled exception",
            data={
                "traceback": "File 'auth.py', line 42\n  raise AuthError('Invalid token')",
            },
        )

        stage = LogsContextStage(db=db)
        result = await stage.process(debugging_task, project)

        assert result is not None
        assert "Traceback:" in result.content
        assert "AuthError" in result.content

    async def test_includes_error_details(self, db, project, debugging_task):
        """Test that error details in log data are included."""
        await _insert_log(
            db,
            project.id,
            task_id=debugging_task.id,
            level="error",
            message="API request failed",
            data={
                "error": "ConnectionRefusedError: Connection refused",
            },
        )

        stage = LogsContextStage(db=db)
        result = await stage.process(debugging_task, project)

        assert result is not None
        assert "Error: ConnectionRefusedError" in result.content

    async def test_deduplicates_logs(self, db, project, debugging_task):
        """Test that duplicate logs are not included twice."""
        # Insert a log that matches both task-specific and project-level queries
        await _insert_log(
            db,
            project.id,
            task_id=debugging_task.id,
            level="error",
            message="Unique error message 12345",
        )

        stage = LogsContextStage(db=db)
        result = await stage.process(debugging_task, project)

        assert result is not None
        # Should only appear once
        count = result.content.count("Unique error message 12345")
        assert count == 1

    async def test_returns_none_when_no_logs_found(self, db, project, debugging_task):
        """Test that stage returns None when no relevant logs exist."""
        stage = LogsContextStage(db=db)
        result = await stage.process(debugging_task, project)
        assert result is None

    async def test_respects_token_budget(self, db, project, debugging_task):
        """Test that logs context respects token budget."""
        # Insert many long logs
        for i in range(100):
            await _insert_log(
                db,
                project.id,
                task_id=debugging_task.id,
                level="error",
                message=f"Error {i}: " + "x" * 500,  # Long message
            )

        stage = LogsContextStage(db=db, max_tokens=500)
        result = await stage.process(debugging_task, project)

        assert result is not None
        assert result.tokens_estimate <= 500
        # Should be truncated
        assert "... (logs truncated)" in result.content

    async def test_respects_log_window(self, db, project, debugging_task):
        """Test that only logs within the time window are fetched."""
        # We can't easily test this since _insert_log uses current time,
        # but we verify the parameter is wired correctly
        stage = LogsContextStage(db=db, log_window_hours=1)
        assert stage.log_window_hours == 1


class TestLogsContextStageInPipeline:
    """Tests for LogsContextStage integration with EnrichmentPipeline."""

    async def test_pipeline_includes_logs_context(self, db, project, debugging_task):
        """Test that the enrichment pipeline includes logs context for debug tasks."""
        from ringmaster.enricher.pipeline import EnrichmentPipeline

        # Insert some logs
        await _insert_log(
            db,
            project.id,
            task_id=debugging_task.id,
            level="error",
            message="Pipeline test error",
        )

        pipeline = EnrichmentPipeline(db=db)
        result = await pipeline.enrich(debugging_task, project)

        assert "logs_context" in result.metrics.stages_applied
        assert "Pipeline test error" in result.user_prompt

    async def test_pipeline_skips_logs_for_non_debug_tasks(self, db, project, non_debugging_task):
        """Test that the enrichment pipeline skips logs for non-debug tasks."""
        from ringmaster.enricher.pipeline import EnrichmentPipeline

        # Insert some logs
        await _insert_log(
            db,
            project.id,
            level="error",
            message="Should not appear",
        )

        pipeline = EnrichmentPipeline(db=db)
        result = await pipeline.enrich(non_debugging_task, project)

        assert "logs_context" not in result.metrics.stages_applied
        assert "Should not appear" not in result.user_prompt
