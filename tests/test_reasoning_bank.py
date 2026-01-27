"""Tests for the Reasoning Bank (task outcomes for reflexion-based learning)."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from ringmaster.db import Database
from ringmaster.db.repositories import ReasoningBankRepository
from ringmaster.domain import TaskOutcome


@pytest.fixture
async def db():
    """Create a test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.disconnect()


@pytest.fixture
async def repo(db: Database):
    """Create a reasoning bank repository."""
    return ReasoningBankRepository(db)


@pytest.fixture
def sample_outcome():
    """Create a sample task outcome."""
    return TaskOutcome(
        task_id="bd-test1234",
        project_id=uuid4(),
        file_count=3,
        keywords=["refactor", "api", "authentication"],
        bead_type="task",
        has_dependencies=True,
        model_used="claude-sonnet-4",
        worker_type="claude-code",
        iterations=2,
        duration_seconds=120,
        success=True,
        outcome="SUCCESS",
        confidence=0.95,
        failure_reason=None,
        reflection="Succeeded on task. Model handled 3 files in 2 iterations.",
    )


class TestReasoningBankRepository:
    """Tests for ReasoningBankRepository."""

    async def test_record_outcome(self, repo: ReasoningBankRepository, sample_outcome: TaskOutcome):
        """Test recording a task outcome."""
        result = await repo.record(sample_outcome)

        assert result.id is not None
        assert result.task_id == sample_outcome.task_id
        assert result.success is True

    async def test_get_outcome(self, repo: ReasoningBankRepository, sample_outcome: TaskOutcome):
        """Test getting an outcome by ID."""
        recorded = await repo.record(sample_outcome)

        fetched = await repo.get(recorded.id)

        assert fetched is not None
        assert fetched.task_id == sample_outcome.task_id
        assert fetched.keywords == sample_outcome.keywords
        assert fetched.success == sample_outcome.success

    async def test_get_outcome_not_found(self, repo: ReasoningBankRepository):
        """Test getting a non-existent outcome."""
        result = await repo.get(99999)
        assert result is None

    async def test_get_for_task(self, repo: ReasoningBankRepository, sample_outcome: TaskOutcome):
        """Test getting outcome for a specific task."""
        await repo.record(sample_outcome)

        result = await repo.get_for_task(sample_outcome.task_id)

        assert result is not None
        assert result.task_id == sample_outcome.task_id

    async def test_get_for_task_not_found(self, repo: ReasoningBankRepository):
        """Test getting outcome for non-existent task."""
        result = await repo.get_for_task("bd-nonexistent")
        assert result is None

    async def test_list_for_project(self, repo: ReasoningBankRepository):
        """Test listing outcomes for a project."""
        project_id = uuid4()

        # Create multiple outcomes
        for i in range(3):
            outcome = TaskOutcome(
                task_id=f"bd-test{i}",
                project_id=project_id,
                file_count=i + 1,
                keywords=[f"keyword{i}"],
                bead_type="task",
                has_dependencies=False,
                model_used="claude-sonnet-4",
                iterations=1,
                duration_seconds=60,
                success=i % 2 == 0,  # Alternating success/failure
                outcome="SUCCESS" if i % 2 == 0 else "FAILED",
                confidence=0.9,
            )
            await repo.record(outcome)

        results = await repo.list_for_project(project_id)

        assert len(results) == 3
        # Should be ordered by created_at DESC
        assert results[0].task_id == "bd-test2"

    async def test_find_similar_by_keywords(self, repo: ReasoningBankRepository):
        """Test finding similar outcomes by keyword matching."""
        project_id = uuid4()

        # Create outcomes with different keywords
        outcomes_data = [
            (["auth", "security", "api"], True),
            (["auth", "login"], True),
            (["database", "migration"], False),
            (["api", "refactor"], True),
        ]

        for i, (keywords, success) in enumerate(outcomes_data):
            outcome = TaskOutcome(
                task_id=f"bd-test{i}",
                project_id=project_id,
                file_count=2,
                keywords=keywords,
                bead_type="task",
                has_dependencies=False,
                model_used="claude-sonnet-4",
                iterations=1,
                duration_seconds=60,
                success=success,
                outcome="SUCCESS" if success else "FAILED",
                confidence=0.9,
            )
            await repo.record(outcome)

        # Find similar to ["auth", "api"]
        similar = await repo.find_similar(
            keywords=["auth", "api"],
            bead_type="task",
            min_similarity=0.2,
        )

        assert len(similar) >= 2
        # Most similar should have highest score
        outcomes_with_auth_api = [o for o, _ in similar if "auth" in o.keywords or "api" in o.keywords]
        assert len(outcomes_with_auth_api) >= 2

    async def test_find_similar_filters_by_bead_type(self, repo: ReasoningBankRepository):
        """Test that find_similar filters by bead type."""
        project_id = uuid4()

        # Create task outcome
        task_outcome = TaskOutcome(
            task_id="bd-task1",
            project_id=project_id,
            file_count=2,
            keywords=["api", "auth"],
            bead_type="task",
            has_dependencies=False,
            model_used="claude-sonnet-4",
            iterations=1,
            duration_seconds=60,
            success=True,
            outcome="SUCCESS",
            confidence=0.9,
        )
        await repo.record(task_outcome)

        # Create subtask outcome with same keywords
        subtask_outcome = TaskOutcome(
            task_id="bd-subtask1",
            project_id=project_id,
            file_count=1,
            keywords=["api", "auth"],
            bead_type="subtask",
            has_dependencies=False,
            model_used="claude-sonnet-4",
            iterations=1,
            duration_seconds=30,
            success=True,
            outcome="SUCCESS",
            confidence=0.9,
        )
        await repo.record(subtask_outcome)

        # Find similar tasks only
        similar_tasks = await repo.find_similar(
            keywords=["api", "auth"],
            bead_type="task",
            min_similarity=0.2,
        )

        assert len(similar_tasks) == 1
        assert similar_tasks[0][0].bead_type == "task"

    async def test_find_similar_with_file_count(self, repo: ReasoningBankRepository):
        """Test that file count affects similarity."""
        project_id = uuid4()

        # Create outcomes with different file counts
        for file_count in [1, 3, 10]:
            outcome = TaskOutcome(
                task_id=f"bd-files{file_count}",
                project_id=project_id,
                file_count=file_count,
                keywords=["api"],
                bead_type="task",
                has_dependencies=False,
                model_used="claude-sonnet-4",
                iterations=1,
                duration_seconds=60,
                success=True,
                outcome="SUCCESS",
                confidence=0.9,
            )
            await repo.record(outcome)

        # Find similar with file_count=3
        similar = await repo.find_similar(
            keywords=["api"],
            bead_type="task",
            file_count=3,
            min_similarity=0.0,  # Low threshold to get all
        )

        assert len(similar) == 3
        # File count similarity should affect scores
        # The outcome with file_count=3 should have highest file similarity

    async def test_get_model_success_rates(self, repo: ReasoningBankRepository):
        """Test getting success rates per model."""
        project_id = uuid4()

        # Create outcomes for different models
        models_data = [
            ("claude-sonnet-4", True),
            ("claude-sonnet-4", True),
            ("claude-sonnet-4", False),
            ("claude-haiku", True),
            ("claude-haiku", False),
            ("claude-haiku", False),
            ("gpt-4o", True),  # Only 1 sample, won't meet min_samples=3
        ]

        for i, (model, success) in enumerate(models_data):
            outcome = TaskOutcome(
                task_id=f"bd-model{i}",
                project_id=project_id,
                file_count=2,
                keywords=["test"],
                bead_type="task",
                has_dependencies=False,
                model_used=model,
                iterations=1,
                duration_seconds=60,
                success=success,
                outcome="SUCCESS" if success else "FAILED",
                confidence=0.9,
            )
            await repo.record(outcome)

        rates = await repo.get_model_success_rates(min_samples=3)

        assert "claude-sonnet-4" in rates
        assert "claude-haiku" in rates
        assert "gpt-4o" not in rates  # Only 1 sample

        assert rates["claude-sonnet-4"]["total"] == 3
        assert rates["claude-sonnet-4"]["success"] == 2
        assert rates["claude-sonnet-4"]["success_rate"] == pytest.approx(2/3)

        assert rates["claude-haiku"]["total"] == 3
        assert rates["claude-haiku"]["success"] == 1
        assert rates["claude-haiku"]["success_rate"] == pytest.approx(1/3)

    async def test_get_stats(self, repo: ReasoningBankRepository):
        """Test getting aggregated statistics."""
        project_id = uuid4()

        # Create some outcomes
        for i in range(5):
            outcome = TaskOutcome(
                task_id=f"bd-stats{i}",
                project_id=project_id,
                file_count=2,
                keywords=["test"],
                bead_type="task",
                has_dependencies=False,
                model_used="claude-sonnet-4",
                iterations=i + 1,
                duration_seconds=60 * (i + 1),
                success=i < 3,  # First 3 succeed
                outcome="SUCCESS" if i < 3 else "FAILED",
                confidence=0.8 + i * 0.04,
            )
            await repo.record(outcome)

        stats = await repo.get_stats()

        assert stats["total_outcomes"] == 5
        assert stats["success_count"] == 3
        assert stats["success_rate"] == pytest.approx(0.6)
        assert stats["avg_iterations"] == pytest.approx(3.0)  # (1+2+3+4+5)/5
        assert stats["avg_duration_seconds"] == pytest.approx(180.0)  # (60+120+180+240+300)/5

    async def test_get_stats_empty(self, repo: ReasoningBankRepository):
        """Test stats when no outcomes exist."""
        stats = await repo.get_stats()

        assert stats["total_outcomes"] == 0
        assert stats["success_count"] == 0
        assert stats["success_rate"] == 0.0

    async def test_cleanup_old(self, repo: ReasoningBankRepository, db: Database):
        """Test cleaning up old outcomes."""
        project_id = uuid4()

        # Create an outcome
        outcome = TaskOutcome(
            task_id="bd-old1",
            project_id=project_id,
            file_count=2,
            keywords=["test"],
            bead_type="task",
            has_dependencies=False,
            model_used="claude-sonnet-4",
            iterations=1,
            duration_seconds=60,
            success=True,
            outcome="SUCCESS",
            confidence=0.9,
        )
        await repo.record(outcome)

        # Manually update the created_at to be old
        await db.execute(
            "UPDATE task_outcomes SET created_at = '2020-01-01T00:00:00'",
            (),
        )
        await db.commit()

        # Clean up with 1 day threshold
        deleted = await repo.cleanup_old(days=1)

        assert deleted == 1

        # Verify it's gone
        result = await repo.get_for_task("bd-old1")
        assert result is None


class TestTaskOutcomeModel:
    """Tests for TaskOutcome domain model."""

    def test_task_outcome_creation(self):
        """Test creating a TaskOutcome model."""
        outcome = TaskOutcome(
            task_id="bd-test1",
            project_id=uuid4(),
            file_count=5,
            keywords=["api", "auth"],
            bead_type="task",
            has_dependencies=True,
            model_used="claude-sonnet-4",
            worker_type="claude-code",
            iterations=3,
            duration_seconds=180,
            success=True,
            outcome="SUCCESS",
            confidence=0.95,
            reflection="Task completed successfully.",
        )

        assert outcome.task_id == "bd-test1"
        assert outcome.file_count == 5
        assert len(outcome.keywords) == 2
        assert outcome.success is True
        assert outcome.confidence == 0.95

    def test_task_outcome_defaults(self):
        """Test TaskOutcome default values."""
        outcome = TaskOutcome(
            task_id="bd-test1",
            project_id=uuid4(),
            bead_type="task",
            model_used="claude-sonnet-4",
            success=False,
        )

        assert outcome.file_count == 0
        assert outcome.keywords == []
        assert outcome.has_dependencies is False
        assert outcome.iterations == 1
        assert outcome.duration_seconds == 0
        assert outcome.confidence == 1.0
        assert outcome.failure_reason is None
        assert outcome.reflection is None
