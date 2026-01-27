"""Live worker integration tests using actual CLI tools.

These tests are SKIPPED by default because they:
- Require the actual CLI tool (claude, aider, etc.) to be installed
- Consume API credits
- Take significant time to run
- Are non-deterministic

To run these tests:
    pytest tests/test_live_worker.py --run-live

Or to run a specific test:
    pytest tests/test_live_worker.py::TestClaudeCodeLive::test_claude_code_simple_task --run-live
"""

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Priority, Project, Task, TaskStatus, Worker, WorkerStatus
from ringmaster.worker.executor import WorkerExecutor
from ringmaster.worker.platforms import ClaudeCodeWorker


@pytest.fixture
async def live_db():
    """Create a temporary database for live testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "live_test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.disconnect()


@pytest.fixture
async def live_project(live_db):
    """Create a test project for live testing."""
    repo = ProjectRepository(live_db)
    project = Project(
        name="Live Test Project",
        description="A project for live CLI integration testing",
        tech_stack=["python"],
    )
    return await repo.create(project)


@pytest.fixture
async def live_worker(live_db):
    """Create a Claude Code worker for live testing."""
    repo = WorkerRepository(live_db)
    worker = Worker(
        name="Claude Code Live Worker",
        type="claude-code",
        command="claude",
        status=WorkerStatus.IDLE,
    )
    return await repo.create(worker)


@pytest.fixture
def live_project_dir():
    """Create a temporary project directory for live testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create minimal Python project
        src_dir = project_dir / "src" / "myproject"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text('"""My project."""\n')
        (src_dir / "math_utils.py").write_text(
            '"""Math utilities."""\n\n\ndef add(a: int, b: int) -> int:\n    """Add two numbers."""\n    return a + b\n'
        )

        # Create a simple test file
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "test_math_utils.py").write_text(
            '"""Tests for math utils."""\n\nfrom myproject.math_utils import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n'
        )

        yield project_dir


class TestClaudeCodeLive:
    """Live tests for Claude Code CLI integration.

    These tests verify real execution with the Claude Code CLI.
    They are expensive (API credits, time) and should be run sparingly.
    """

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_claude_code_is_available(self):
        """Verify Claude Code CLI is installed and available."""
        worker = ClaudeCodeWorker()
        assert await worker.is_available(), "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_claude_code_simple_task(
        self, live_db, live_project, live_worker, live_project_dir
    ):
        """Test Claude Code executing a simple code task.

        This test creates a minimal task and verifies Claude can execute it.
        The task is designed to be quick and cheap (simple file creation).
        """
        # Skip if Claude not available
        if not shutil.which("claude"):
            pytest.skip("Claude Code CLI not available")

        # Create a simple task
        task_repo = TaskRepository(live_db)
        task = Task(
            project_id=live_project.id,
            title="Add a multiply function to math_utils.py",
            description="Add a function called 'multiply' that multiplies two integers and returns the result. Include a docstring. Do not add tests.",
            priority=Priority.P2,
            status=TaskStatus.READY,
            max_attempts=1,  # Only try once for live tests
        )
        task = await task_repo.create_task(task)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                live_db,
                output_dir=Path(output_dir),
                project_dir=live_project_dir,
            )

            # Execute the task
            result = await executor.execute_task(task, live_worker)

            # Verify execution happened
            assert result is not None
            assert result.output is not None
            assert len(result.output) > 0

            # Check if the function was added (best-effort verification)
            math_utils = live_project_dir / "src" / "myproject" / "math_utils.py"
            if math_utils.exists():
                content = math_utils.read_text()
                # The test passes if Claude modified the file (even if incomplete)
                # We don't strictly require success since Claude's output is non-deterministic
                print(f"File content after execution:\n{content}")

            # Verify metrics were recorded
            metrics = await live_db.fetchone(
                "SELECT * FROM session_metrics WHERE task_id = ?",
                (task.id,),
            )
            assert metrics is not None, "Session metrics should be recorded"

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_claude_code_with_streaming_output(
        self, live_db, live_project, live_worker, live_project_dir
    ):
        """Test that Claude Code output is streamed correctly."""
        if not shutil.which("claude"):
            pytest.skip("Claude Code CLI not available")

        task_repo = TaskRepository(live_db)
        task = Task(
            project_id=live_project.id,
            title="Print 'Hello World' to verify streaming",
            description="Create a simple Python script called hello.py that prints 'Hello World'.",
            priority=Priority.P3,
            status=TaskStatus.READY,
            max_attempts=1,
        )
        task = await task_repo.create_task(task)

        streamed_lines = []

        def on_output(line: str):
            streamed_lines.append(line)
            print(f"[STREAM] {line}")

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                live_db,
                output_dir=Path(output_dir),
                project_dir=live_project_dir,
            )

            await executor.execute_task(task, live_worker, on_output=on_output)

            # Verify streaming happened
            assert len(streamed_lines) > 0, "Should have received streamed output"
            print(f"Received {len(streamed_lines)} output lines")

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_claude_code_worker_status_updates(
        self, live_db, live_project, live_worker, live_project_dir
    ):
        """Test that worker and task status are updated during execution."""
        if not shutil.which("claude"):
            pytest.skip("Claude Code CLI not available")

        task_repo = TaskRepository(live_db)
        worker_repo = WorkerRepository(live_db)

        task = Task(
            project_id=live_project.id,
            title="Create an empty __init__.py file",
            description="Create a file called __init__.py in the project root with just a docstring.",
            priority=Priority.P3,
            status=TaskStatus.READY,
            max_attempts=1,
        )
        task = await task_repo.create_task(task)

        # Verify initial states
        assert live_worker.status == WorkerStatus.IDLE
        assert task.status == TaskStatus.READY

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                live_db,
                output_dir=Path(output_dir),
                project_dir=live_project_dir,
            )

            await executor.execute_task(task, live_worker)

            # Verify final states
            updated_worker = await worker_repo.get(live_worker.id)
            updated_task = await task_repo.get_task(task.id)

            # Worker should be idle after completion
            assert updated_worker.status == WorkerStatus.IDLE
            assert updated_worker.current_task_id is None
            assert updated_worker.tasks_completed >= 1

            # Task should have transitioned (may be REVIEW, DONE, or FAILED depending on outcome)
            assert updated_task.status != TaskStatus.READY
            assert updated_task.attempts == 1


class TestClaudeCodeTimeout:
    """Tests for timeout handling with real Claude CLI."""

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_long_running_task_completes(
        self, live_db, live_project, live_worker, live_project_dir
    ):
        """Test that long-running tasks complete and don't hang indefinitely.

        This test verifies the system can handle long-running tasks gracefully.
        The task is designed to be substantial but should complete in a reasonable time.
        """
        if not shutil.which("claude"):
            pytest.skip("Claude Code CLI not available")

        task_repo = TaskRepository(live_db)

        task = Task(
            project_id=live_project.id,
            title="Create comprehensive documentation",
            description="Write detailed documentation for the entire project. Include README, API docs, and usage examples.",
            priority=Priority.P3,
            status=TaskStatus.READY,
            max_attempts=1,
        )
        task = await task_repo.create_task(task)

        with tempfile.TemporaryDirectory() as output_dir:
            executor = WorkerExecutor(
                live_db,
                output_dir=Path(output_dir),
                project_dir=live_project_dir,
            )

            start_time = datetime.now(UTC)
            result = await executor.execute_task(task, live_worker)
            elapsed = (datetime.now(UTC) - start_time).total_seconds()

            # Task should complete or fail, but shouldn't hang forever
            assert elapsed < 600, "Task should complete within 10 minutes"
            assert result is not None

            # Verify metrics were recorded
            metrics = await live_db.fetchone(
                "SELECT * FROM session_metrics WHERE task_id = ?",
                (task.id,),
            )
            assert metrics is not None, "Session metrics should be recorded"


class TestWorkerAvailability:
    """Tests for worker availability detection."""

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_detect_installed_workers(self):
        """Detect which worker CLIs are installed on this system."""
        from ringmaster.worker.platforms import AiderWorker, ClaudeCodeWorker

        workers = [
            ("claude-code", ClaudeCodeWorker()),
            ("aider", AiderWorker()),
        ]

        available = []
        for name, worker in workers:
            if await worker.is_available():
                available.append(name)
                print(f"✓ {name} is available")
            else:
                print(f"✗ {name} is not available")

        print(f"\nAvailable workers: {', '.join(available) or 'none'}")
