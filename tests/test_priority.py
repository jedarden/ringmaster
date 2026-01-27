"""Tests for priority calculation and inheritance."""

import tempfile
from pathlib import Path

import pytest

from ringmaster.db.connection import Database
from ringmaster.db.repositories import ProjectRepository, TaskRepository
from ringmaster.domain import Dependency, Priority, Project, Task, TaskStatus
from ringmaster.queue.priority import PriorityCalculator


def make_dependency(child_id: str, parent_id: str) -> Dependency:
    """Helper to create a Dependency object."""
    return Dependency(child_id=child_id, parent_id=parent_id)


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
    project = Project(name="Test Project")
    await repo.create(project)
    return project


@pytest.fixture
async def calculator(db):
    """Create a priority calculator."""
    return PriorityCalculator(db)


class TestPriorityCalculator:
    """Tests for the PriorityCalculator class."""

    async def test_recalculate_empty_project(self, db, project, calculator):
        """Test recalculating priorities for an empty project."""
        updated = await calculator.recalculate_priorities(project.id)
        assert updated == 0

    async def test_recalculate_single_task(self, db, project, calculator):
        """Test recalculating priorities for a single task."""
        task_repo = TaskRepository(db)
        task = Task(
            project_id=project.id,
            title="Single task",
            priority=Priority.P1,
        )
        await task_repo.create_task(task)

        updated = await calculator.recalculate_priorities(project.id)
        assert updated == 1

        updated_task = await task_repo.get_task(task.id)
        assert updated_task.combined_priority > 0

    async def test_pagerank_with_dependencies(self, db, project, calculator):
        """Test that tasks with more dependents get higher PageRank."""
        task_repo = TaskRepository(db)

        # Create a hub task (blocker for many tasks)
        hub_task = Task(
            project_id=project.id,
            title="Hub task (blocks many)",
            priority=Priority.P2,
        )
        await task_repo.create_task(hub_task)

        # Create tasks that depend on the hub
        dependent_tasks = []
        for i in range(5):
            task = Task(
                project_id=project.id,
                title=f"Dependent task {i}",
                priority=Priority.P2,
            )
            await task_repo.create_task(task)
            await task_repo.add_dependency(make_dependency(task.id, hub_task.id))
            dependent_tasks.append(task)

        # Create an isolated task
        isolated_task = Task(
            project_id=project.id,
            title="Isolated task",
            priority=Priority.P2,
        )
        await task_repo.create_task(isolated_task)

        await calculator.recalculate_priorities(project.id)

        # Hub task should have higher PageRank (more dependents)
        updated_hub = await task_repo.get_task(hub_task.id)
        updated_isolated = await task_repo.get_task(isolated_task.id)

        assert updated_hub.pagerank_score > updated_isolated.pagerank_score

    async def test_critical_path_identification(self, db, project, calculator):
        """Test that critical path tasks are identified."""
        task_repo = TaskRepository(db)

        # Create a linear chain: A -> B -> C
        task_a = Task(project_id=project.id, title="Task A", priority=Priority.P2)
        task_b = Task(project_id=project.id, title="Task B", priority=Priority.P2)
        task_c = Task(project_id=project.id, title="Task C", priority=Priority.P2)

        await task_repo.create_task(task_a)
        await task_repo.create_task(task_b)
        await task_repo.create_task(task_c)

        await task_repo.add_dependency(make_dependency(task_b.id, task_a.id))  # B depends on A
        await task_repo.add_dependency(make_dependency(task_c.id, task_b.id))  # C depends on B

        await calculator.recalculate_priorities(project.id)

        # All tasks in the chain should be on critical path
        updated_a = await task_repo.get_task(task_a.id)
        updated_b = await task_repo.get_task(task_b.id)
        updated_c = await task_repo.get_task(task_c.id)

        assert updated_a.on_critical_path
        assert updated_b.on_critical_path
        assert updated_c.on_critical_path


class TestPriorityInheritance:
    """Tests for priority inheritance feature."""

    async def test_blocked_task_inherits_priority_to_blocker(self, db, project, calculator):
        """Test that a blocker inherits priority from a blocked high-priority task."""
        task_repo = TaskRepository(db)

        # Create a low-priority blocker task
        blocker = Task(
            project_id=project.id,
            title="Low priority blocker",
            priority=Priority.P4,  # Low priority
            status=TaskStatus.READY,
        )
        await task_repo.create_task(blocker)

        # Create a high-priority task that is blocked
        blocked = Task(
            project_id=project.id,
            title="High priority blocked task",
            priority=Priority.P0,  # High priority
            status=TaskStatus.BLOCKED,
        )
        await task_repo.create_task(blocked)

        # Add dependency: blocked depends on blocker
        await task_repo.add_dependency(make_dependency(blocked.id, blocker.id))

        await calculator.recalculate_priorities(project.id)

        updated_blocker = await task_repo.get_task(blocker.id)
        updated_blocked = await task_repo.get_task(blocked.id)

        # Blocker should inherit priority from blocked task
        # Note: combined_priority includes inheritance
        assert updated_blocker.combined_priority >= updated_blocked.combined_priority

    async def test_completed_blocker_does_not_inherit(self, db, project, calculator):
        """Test that completed blockers don't inherit priority."""
        task_repo = TaskRepository(db)

        # Create a completed blocker
        blocker = Task(
            project_id=project.id,
            title="Completed blocker",
            priority=Priority.P4,
            status=TaskStatus.DONE,  # Already completed
        )
        await task_repo.create_task(blocker)

        # Create a blocked high-priority task
        blocked = Task(
            project_id=project.id,
            title="Blocked task",
            priority=Priority.P0,
            status=TaskStatus.BLOCKED,
        )
        await task_repo.create_task(blocked)

        await task_repo.add_dependency(make_dependency(blocked.id, blocker.id))

        await calculator.recalculate_priorities(project.id)

        updated_blocker = await task_repo.get_task(blocker.id)

        # Completed blocker should have low priority (no inheritance)
        # Combined priority should be based on P4, not inherited
        assert updated_blocker.combined_priority < 0.5  # P4 weight is 0.2

    async def test_transitive_inheritance(self, db, project, calculator):
        """Test that priority inheritance is transitive (A blocks B blocks C)."""
        task_repo = TaskRepository(db)

        # Create a chain: A (low) <- B (blocked) <- C (blocked, high priority)
        task_a = Task(
            project_id=project.id,
            title="Task A (blocker)",
            priority=Priority.P4,
            status=TaskStatus.READY,
        )
        task_b = Task(
            project_id=project.id,
            title="Task B (blocked by A, blocks C)",
            priority=Priority.P3,
            status=TaskStatus.BLOCKED,
        )
        task_c = Task(
            project_id=project.id,
            title="Task C (blocked by B, high priority)",
            priority=Priority.P0,
            status=TaskStatus.BLOCKED,
        )

        await task_repo.create_task(task_a)
        await task_repo.create_task(task_b)
        await task_repo.create_task(task_c)

        await task_repo.add_dependency(make_dependency(task_b.id, task_a.id))  # B depends on A
        await task_repo.add_dependency(make_dependency(task_c.id, task_b.id))  # C depends on B

        await calculator.recalculate_priorities(project.id)

        updated_a = await task_repo.get_task(task_a.id)
        updated_c = await task_repo.get_task(task_c.id)

        # A should inherit priority from the chain (through B from C)
        # All should have similar combined priority due to inheritance
        assert updated_a.combined_priority >= updated_c.combined_priority * 0.9

    async def test_no_inheritance_for_non_blocked_tasks(self, db, project, calculator):
        """Test that non-blocked tasks don't trigger inheritance."""
        task_repo = TaskRepository(db)

        # Create a low-priority blocker
        blocker = Task(
            project_id=project.id,
            title="Low priority blocker",
            priority=Priority.P4,
            status=TaskStatus.READY,
        )
        await task_repo.create_task(blocker)

        # Create a high-priority task that is READY (not blocked)
        dependent = Task(
            project_id=project.id,
            title="High priority ready task",
            priority=Priority.P0,
            status=TaskStatus.READY,  # Not blocked!
        )
        await task_repo.create_task(dependent)

        await task_repo.add_dependency(make_dependency(dependent.id, blocker.id))

        await calculator.recalculate_priorities(project.id)

        updated_blocker = await task_repo.get_task(blocker.id)
        updated_dependent = await task_repo.get_task(dependent.id)

        # Blocker should NOT inherit priority because dependent is not blocked
        # Blocker priority should be lower than dependent priority
        assert updated_blocker.combined_priority < updated_dependent.combined_priority

    async def test_multiple_blocked_tasks_highest_priority_wins(self, db, project, calculator):
        """Test that when multiple tasks are blocked, the highest priority propagates."""
        task_repo = TaskRepository(db)

        # Create a blocker
        blocker = Task(
            project_id=project.id,
            title="Shared blocker",
            priority=Priority.P4,
            status=TaskStatus.READY,
        )
        await task_repo.create_task(blocker)

        # Create multiple blocked tasks with different priorities
        blocked_p2 = Task(
            project_id=project.id,
            title="Blocked P2",
            priority=Priority.P2,
            status=TaskStatus.BLOCKED,
        )
        blocked_p0 = Task(
            project_id=project.id,
            title="Blocked P0 (highest)",
            priority=Priority.P0,
            status=TaskStatus.BLOCKED,
        )

        await task_repo.create_task(blocked_p2)
        await task_repo.create_task(blocked_p0)

        await task_repo.add_dependency(make_dependency(blocked_p2.id, blocker.id))
        await task_repo.add_dependency(make_dependency(blocked_p0.id, blocker.id))

        await calculator.recalculate_priorities(project.id)

        updated_blocker = await task_repo.get_task(blocker.id)
        updated_p0 = await task_repo.get_task(blocked_p0.id)

        # Blocker should inherit the highest blocked priority (P0)
        assert updated_blocker.combined_priority >= updated_p0.combined_priority
