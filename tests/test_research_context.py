"""Tests for ResearchContextStage in the enrichment pipeline.

Based on docs/04-context-enrichment.md section 2:
- Prior agent task outputs (when task is related)
- Task completion summaries
- Related exploration/spike results
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ringmaster.db import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Priority, Project, Task, TaskStatus, TaskType, Worker
from ringmaster.enricher.stages import ResearchContextStage


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
async def worker(db):
    """Create a test worker in the database."""
    w = Worker(
        id="worker-1",
        name="Test Worker",
        type="claude-code",
        command="claude",
    )
    repo = WorkerRepository(db)
    await repo.create(w)
    return w


@pytest.fixture
async def project(db, worker):
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
async def api_task(db, project):
    """Create a task about API development."""
    task = Task(
        id="task-api-1",
        project_id=project.id,
        type=TaskType.TASK,
        title="Implement user authentication endpoint",
        description="Add API endpoint for auth with JWT tokens",
        priority=Priority.P1,
        status=TaskStatus.IN_PROGRESS,
    )
    repo = TaskRepository(db)
    await repo.create_task(task)
    return task


@pytest.fixture
async def unrelated_task(db, project):
    """Create a task unrelated to the others."""
    task = Task(
        id="task-unrelated-1",
        project_id=project.id,
        type=TaskType.TASK,
        title="Update README",
        description="Fix typos in documentation",
        priority=Priority.P3,
        status=TaskStatus.IN_PROGRESS,
    )
    repo = TaskRepository(db)
    await repo.create_task(task)
    return task


async def _create_completed_task(
    db, project, task_id, title, description, output_summary=None
):
    """Helper to create a completed task with optional output summary."""
    task = Task(
        id=task_id,
        project_id=project.id,
        type=TaskType.TASK,
        title=title,
        description=description,
        priority=Priority.P2,
        status=TaskStatus.DONE,
    )
    repo = TaskRepository(db)
    await repo.create_task(task)

    # Update to done status with completed_at
    await db.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (datetime.now(UTC).isoformat(), task_id),
    )
    await db.commit()

    # Add session_metrics with output_summary if provided
    if output_summary:
        await db.execute(
            """
            INSERT INTO session_metrics
            (task_id, worker_id, iteration, started_at, ended_at, success, output_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                "worker-1",
                1,
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                True,
                output_summary,
            ),
        )
        await db.commit()

    return task


class TestResearchContextStageKeywordExtraction:
    """Tests for keyword extraction logic."""

    def test_extracts_technical_keywords(self):
        """Test that technical keywords are extracted correctly."""
        stage = ResearchContextStage()

        text = "Implement API endpoint for user authentication with JWT tokens"
        keywords = stage._extract_keywords(text)

        assert "api" in keywords
        assert "endpoint" in keywords
        assert "authentication" in keywords
        assert "jwt" in keywords

    def test_ignores_non_technical_words(self):
        """Test that common words are not extracted."""
        stage = ResearchContextStage()

        text = "The quick brown fox jumps over the lazy dog"
        keywords = stage._extract_keywords(text)

        assert len(keywords) == 0

    def test_handles_empty_text(self):
        """Test handling of empty or None text."""
        stage = ResearchContextStage()

        assert stage._extract_keywords("") == set()
        assert stage._extract_keywords(None) == set()


class TestResearchContextStageRelevanceScoring:
    """Tests for relevance scoring between tasks."""

    def test_high_relevance_for_similar_tasks(self):
        """Test that similar tasks get high relevance scores."""
        stage = ResearchContextStage()

        current_keywords = {"api", "endpoint", "authentication", "auth", "jwt"}

        relevance = stage._calculate_relevance(
            current_keywords=current_keywords,
            current_title="Add API auth endpoint",
            candidate_title="Implement API authentication endpoint",
            candidate_description="JWT auth token validation for the API endpoint",
        )

        # Should have high relevance due to keyword overlap
        assert relevance > 0.4  # Multiple overlapping keywords

    def test_low_relevance_for_unrelated_tasks(self):
        """Test that unrelated tasks get low relevance scores."""
        stage = ResearchContextStage()

        current_keywords = {"api", "endpoint", "authentication"}

        relevance = stage._calculate_relevance(
            current_keywords=current_keywords,
            current_title="Add auth endpoint",
            candidate_title="Update documentation",
            candidate_description="Fix typos in README file",
        )

        # Should have low relevance due to no keyword overlap
        assert relevance < 0.3

    def test_title_overlap_contributes_to_relevance(self):
        """Test that title word overlap contributes to relevance."""
        stage = ResearchContextStage()

        current_keywords = set()  # No keywords

        relevance = stage._calculate_relevance(
            current_keywords=current_keywords,
            current_title="Add user profile page",
            candidate_title="Update user profile settings",
            candidate_description="",
        )

        # Should have some relevance due to title overlap
        assert relevance > 0


class TestResearchContextStageProcess:
    """Tests for the process method."""

    async def test_skips_when_no_database(self, project, api_task):
        """Test that stage skips when no database is configured."""
        stage = ResearchContextStage(db=None)
        result = await stage.process(api_task, project)
        assert result is None

    async def test_skips_when_no_completed_tasks(self, db, project, api_task):
        """Test that stage skips when no completed tasks exist."""
        stage = ResearchContextStage(db=db)
        result = await stage.process(api_task, project)
        assert result is None

    async def test_finds_related_completed_tasks(self, db, project, api_task):
        """Test that related completed tasks are found and included."""
        # Create a completed task related to auth/API with strong keyword overlap
        await _create_completed_task(
            db,
            project,
            "task-prev-auth",
            "Implement API authentication endpoint",
            "Added JWT auth token validation endpoint for API authentication",
            output_summary="Added JWT validation middleware with expiry check",
        )

        # Use a lower threshold to ensure matching
        stage = ResearchContextStage(db=db, min_relevance_score=0.2)
        result = await stage.process(api_task, project)

        assert result is not None
        assert "## Prior Research & Related Work" in result.content
        assert "Implement API authentication endpoint" in result.content
        assert "JWT validation middleware" in result.content
        assert result.tokens_estimate > 0

    async def test_excludes_unrelated_tasks(self, db, project, api_task):
        """Test that unrelated completed tasks are excluded."""
        # Create an unrelated completed task
        await _create_completed_task(
            db,
            project,
            "task-unrelated",
            "Update CSS styles",
            "Changed button colors",
            output_summary="Updated button hover effects",
        )

        stage = ResearchContextStage(db=db, min_relevance_score=0.3)
        result = await stage.process(api_task, project)

        # No related tasks should be found
        assert result is None

    async def test_respects_max_results(self, db, project, api_task):
        """Test that max_results limit is respected."""
        # Create multiple related tasks
        for i in range(10):
            await _create_completed_task(
                db,
                project,
                f"task-auth-{i}",
                f"Auth feature {i} with API endpoint",
                f"JWT authentication implementation {i}",
                output_summary=f"Implemented auth feature {i}",
            )

        stage = ResearchContextStage(db=db, max_results=3)
        result = await stage.process(api_task, project)

        assert result is not None
        # Should have at most 3 task sections
        task_count = result.content.count("### ")
        assert task_count <= 3

    async def test_respects_token_budget(self, db, project, api_task):
        """Test that token budget is respected."""
        # Create tasks with long summaries and strong keyword overlap
        for i in range(5):
            await _create_completed_task(
                db,
                project,
                f"task-long-{i}",
                f"API endpoint authentication {i}",
                f"Auth JWT implementation endpoint {i}",
                output_summary="Summary: " + "x" * 1000,
            )

        stage = ResearchContextStage(db=db, max_tokens=500, min_relevance_score=0.2)
        result = await stage.process(api_task, project)

        assert result is not None
        assert result.tokens_estimate <= 500
        assert "... (research context truncated)" in result.content

    async def test_excludes_current_task(self, db, project, api_task):
        """Test that the current task is not included in results."""
        # Complete the current task with a summary
        await db.execute(
            "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), api_task.id),
        )
        await db.execute(
            """
            INSERT INTO session_metrics
            (task_id, worker_id, iteration, started_at, success, output_summary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (api_task.id, "worker-1", 1, datetime.now(UTC).isoformat(), True, "Self summary"),
        )
        await db.commit()

        stage = ResearchContextStage(db=db)
        result = await stage.process(api_task, project)

        # Should not find any tasks (only current task exists)
        assert result is None

    async def test_includes_task_description_as_fallback(self, db, project, api_task):
        """Test that task description is used when no output summary exists."""
        # Create a completed task without output summary
        await _create_completed_task(
            db,
            project,
            "task-no-summary",
            "Setup API authentication",
            "Configure JWT tokens and middleware for API auth",
            output_summary=None,  # No summary
        )

        stage = ResearchContextStage(db=db)
        result = await stage.process(api_task, project)

        assert result is not None
        # Should use description as fallback
        assert "Configure JWT tokens" in result.content

    async def test_formats_relevance_percentage(self, db, project, api_task):
        """Test that relevance is formatted as a percentage."""
        await _create_completed_task(
            db,
            project,
            "task-related",
            "API endpoint authentication",
            "Auth with JWT",
            output_summary="Added auth",
        )

        stage = ResearchContextStage(db=db)
        result = await stage.process(api_task, project)

        assert result is not None
        assert "Relevance:" in result.content
        assert "%" in result.content


class TestResearchContextStageInPipeline:
    """Tests for ResearchContextStage integration with EnrichmentPipeline."""

    async def test_pipeline_includes_research_context(self, db, project, api_task):
        """Test that the enrichment pipeline includes research context."""
        from ringmaster.enricher.pipeline import EnrichmentPipeline

        # Create a related completed task
        await _create_completed_task(
            db,
            project,
            "task-prev",
            "Implement user API endpoint",
            "REST API for users",
            output_summary="Added user CRUD endpoints",
        )

        pipeline = EnrichmentPipeline(db=db)
        result = await pipeline.enrich(api_task, project)

        assert "research_context" in result.metrics.stages_applied
        assert "user CRUD endpoints" in result.user_prompt

    async def test_pipeline_skips_when_no_related_tasks(self, db, project, unrelated_task):
        """Test that the enrichment pipeline skips research when no related tasks."""
        from ringmaster.enricher.pipeline import EnrichmentPipeline

        # Create completed tasks unrelated to the current task
        await _create_completed_task(
            db,
            project,
            "task-auth",
            "Authentication API",
            "JWT auth",
            output_summary="Added auth",
        )

        pipeline = EnrichmentPipeline(db=db)
        result = await pipeline.enrich(unrelated_task, project)

        # Research context should be skipped due to low relevance
        assert "research_context" not in result.metrics.stages_applied
