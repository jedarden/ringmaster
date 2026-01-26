"""Tests for domain models."""

from uuid import UUID

import pytest

from ringmaster.domain import (
    Epic,
    Priority,
    Project,
    Task,
    TaskStatus,
    TaskType,
    Worker,
    WorkerStatus,
)


def test_project_creation():
    """Test creating a project."""
    project = Project(
        name="Test Project",
        description="A test project",
        tech_stack=["python", "fastapi"],
    )

    assert project.name == "Test Project"
    assert project.description == "A test project"
    assert project.tech_stack == ["python", "fastapi"]
    assert isinstance(project.id, UUID)


def test_task_creation():
    """Test creating a task."""
    project = Project(name="Test")
    task = Task(
        project_id=project.id,
        title="Implement feature",
        description="Implement the new feature",
        priority=Priority.P1,
    )

    assert task.title == "Implement feature"
    assert task.priority == Priority.P1
    assert task.status == TaskStatus.DRAFT
    assert task.type == TaskType.TASK
    assert task.id.startswith("bd-")


def test_epic_creation():
    """Test creating an epic."""
    project = Project(name="Test")
    epic = Epic(
        project_id=project.id,
        title="User Authentication",
        acceptance_criteria=["Users can login", "Users can logout"],
    )

    assert epic.title == "User Authentication"
    assert epic.type == TaskType.EPIC
    assert len(epic.acceptance_criteria) == 2


def test_worker_creation():
    """Test creating a worker."""
    worker = Worker(
        name="Claude Worker 1",
        type="claude-code",
        command="claude",
    )

    assert worker.name == "Claude Worker 1"
    assert worker.type == "claude-code"
    assert worker.status == WorkerStatus.OFFLINE
    assert worker.tasks_completed == 0


def test_task_status_values():
    """Test task status enum values."""
    assert TaskStatus.DRAFT.value == "draft"
    assert TaskStatus.READY.value == "ready"
    assert TaskStatus.IN_PROGRESS.value == "in_progress"
    assert TaskStatus.DONE.value == "done"
    assert TaskStatus.FAILED.value == "failed"


def test_priority_values():
    """Test priority enum values."""
    assert Priority.P0.value == "P0"
    assert Priority.P1.value == "P1"
    assert Priority.P2.value == "P2"
    assert Priority.P3.value == "P3"
    assert Priority.P4.value == "P4"
