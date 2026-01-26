"""Tests for worker executor with enrichment pipeline integration."""

import contextlib
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Priority, Project, Task, TaskStatus, Worker, WorkerStatus
from ringmaster.enricher import EnrichmentPipeline
from ringmaster.worker.executor import WorkerExecutor


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
        name="Test Project",
        description="A test project for executor testing",
        tech_stack=["python", "fastapi"],
        repo_url="/tmp/test-repo",
    )
    return await repo.create(project)


@pytest.fixture
async def task(db, project):
    """Create a test task."""
    repo = TaskRepository(db)
    task = Task(
        project_id=project.id,
        title="Implement feature X",
        description="Add the calculate_total function to utils.py",
        priority=Priority.P1,
        status=TaskStatus.READY,
    )
    return await repo.create_task(task)


@pytest.fixture
async def worker(db):
    """Create a test worker."""
    repo = WorkerRepository(db)
    worker = Worker(
        name="Test Claude Worker",
        type="claude-code",
        command="claude",
        status=WorkerStatus.IDLE,
    )
    return await repo.create(worker)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create src directory
        src_dir = project_dir / "src" / "myproject"
        src_dir.mkdir(parents=True)

        # Create utils.py
        (src_dir / "utils.py").write_text('''"""Utility functions."""

def helper_function():
    """A helper function."""
    return "hello"
''')

        # Create __init__.py
        (src_dir / "__init__.py").write_text('"""My project."""\n')
        (project_dir / "src" / "__init__.py").touch()

        yield project_dir


class TestWorkerExecutorInit:
    """Tests for WorkerExecutor initialization."""

    @pytest.mark.asyncio
    async def test_executor_has_enrichment_pipeline(self, db, temp_project_dir):
        """Test that executor lazily creates enrichment pipeline."""
        executor = WorkerExecutor(db, project_dir=temp_project_dir)

        # Pipeline should not be created yet
        assert executor._enrichment_pipeline is None

        # Accessing the property should create it
        pipeline = executor.enrichment_pipeline
        assert isinstance(pipeline, EnrichmentPipeline)
        assert pipeline.project_dir == temp_project_dir
        assert pipeline.db == db

    @pytest.mark.asyncio
    async def test_executor_project_dir_defaults_to_cwd(self, db):
        """Test that executor defaults project_dir to cwd."""
        executor = WorkerExecutor(db)
        assert executor.project_dir == Path.cwd()

    @pytest.mark.asyncio
    async def test_executor_has_project_repo(self, db):
        """Test that executor has project repository."""
        executor = WorkerExecutor(db)
        assert executor.project_repo is not None
        assert isinstance(executor.project_repo, ProjectRepository)


class TestBuildEnrichedPrompt:
    """Tests for enriched prompt building."""

    @pytest.mark.asyncio
    async def test_build_enriched_prompt_includes_all_layers(
        self, db, project, task, temp_project_dir
    ):
        """Test that enriched prompt includes all context layers."""
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            executor = WorkerExecutor(db, project_dir=temp_project_dir)

            # Build the prompt
            prompt = await executor._build_enriched_prompt(task, project, output_path)

            # Should include task context
            assert task.title in prompt
            assert "Implement feature X" in prompt

            # Should include project context
            assert project.name in prompt
            assert "python" in prompt or "fastapi" in prompt

            # Should include instructions
            assert "Instructions" in prompt
            assert "COMPLETE" in prompt

    @pytest.mark.asyncio
    async def test_build_enriched_prompt_saves_prompt_file(
        self, db, project, task, temp_project_dir
    ):
        """Test that enriched prompt is saved to file."""
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            executor = WorkerExecutor(db, project_dir=temp_project_dir)

            await executor._build_enriched_prompt(task, project, output_path)

            # Should have saved prompt file
            prompt_files = list(output_path.glob("prompt_*.md"))
            assert len(prompt_files) == 1

            # File should contain system and user prompts
            content = prompt_files[0].read_text()
            assert "# System Prompt" in content
            assert "# User Prompt" in content

    @pytest.mark.asyncio
    async def test_build_enriched_prompt_updates_context_hash(
        self, db, project, task, temp_project_dir
    ):
        """Test that context hash is updated on task."""
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            executor = WorkerExecutor(db, project_dir=temp_project_dir)

            # Initially no context hash
            assert task.context_hash is None

            await executor._build_enriched_prompt(task, project, output_path)

            # Should have context hash now
            assert task.context_hash is not None
            assert len(task.context_hash) == 16  # sha256[:16]

    @pytest.mark.asyncio
    async def test_build_fallback_prompt_on_enrichment_failure(
        self, db, project, task, temp_project_dir
    ):
        """Test that fallback prompt is used when enrichment fails."""
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            executor = WorkerExecutor(db, project_dir=temp_project_dir)

            # Mock enrichment pipeline to fail
            with patch.object(
                executor.enrichment_pipeline,
                "enrich",
                side_effect=Exception("Enrichment failed"),
            ):
                prompt = await executor._build_enriched_prompt(task, project, output_path)

            # Should use fallback prompt
            assert task.title in prompt
            assert "COMPLETE" in prompt
            assert "Instructions" in prompt


class TestExecuteTask:
    """Tests for task execution with enrichment."""

    @pytest.mark.asyncio
    async def test_execute_task_fails_without_project(self, db, task, worker):
        """Test that execution fails if project doesn't exist."""
        executor = WorkerExecutor(db)

        # Task references a project that doesn't exist in DB
        task.project_id = task.project_id  # Existing ID but project not in DB

        # Delete the project first
        await ProjectRepository(db).delete(task.project_id)

        result = await executor.execute_task(task, worker)

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_task_uses_project_repo_url_as_working_dir(
        self, db, project, task, worker, temp_project_dir
    ):
        """Test that project repo_url is used as working directory."""
        # Update project to have valid repo_url
        project.repo_url = str(temp_project_dir)
        await ProjectRepository(db).update(project)

        executor = WorkerExecutor(db, project_dir=temp_project_dir)

        # Mock the worker interface to capture config
        captured_config = None

        async def mock_start_session(config):
            nonlocal captured_config
            captured_config = config
            raise Exception("Test abort")  # Stop execution after capturing config

        with patch(
            "ringmaster.worker.executor.get_worker"
        ) as mock_get_worker:
            mock_interface = AsyncMock()
            mock_interface.is_available.return_value = True
            mock_interface.start_session = mock_start_session
            mock_get_worker.return_value = mock_interface

            with contextlib.suppress(Exception):
                await executor.execute_task(task, worker)

        # Working dir should be from project repo_url
        assert captured_config is not None
        assert captured_config.working_dir == temp_project_dir


class TestFallbackPrompt:
    """Tests for fallback prompt building."""

    @pytest.mark.asyncio
    async def test_fallback_prompt_contains_task_info(self, db):
        """Test that fallback prompt includes task information."""
        executor = WorkerExecutor(db)
        task = Task(
            project_id=Project(name="Test").id,
            title="Test Task",
            description="Test description",
        )

        prompt = executor._build_fallback_prompt(task)

        assert "Test Task" in prompt
        assert "Test description" in prompt
        assert "Instructions" in prompt
        assert "COMPLETE" in prompt

    @pytest.mark.asyncio
    async def test_fallback_prompt_handles_missing_description(self, db):
        """Test that fallback prompt handles missing description."""
        executor = WorkerExecutor(db)
        task = Task(
            project_id=Project(name="Test").id,
            title="Test Task",
            description=None,
        )

        prompt = executor._build_fallback_prompt(task)

        assert "Test Task" in prompt
        assert "No description provided" in prompt
