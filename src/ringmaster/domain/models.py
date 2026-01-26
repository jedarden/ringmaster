"""Core domain models for Ringmaster.

Based on the Beads-inspired work unit hierarchy:
- Epic: Top-level container (feature, initiative)
- Task: Mid-level work item (single worker, single session)
- Subtask: Granular unit for complex tasks
- Decision: Human-in-the-loop blocking point
- Question: Non-blocking clarification request
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ringmaster.domain.enums import Priority, TaskStatus, TaskType, WorkerStatus


def generate_bead_id() -> str:
    """Generate a Beads-style ID (bd-xxxx)."""
    return f"bd-{uuid4().hex[:8]}"


class Project(BaseModel):
    """A project containing epics and tasks."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    repo_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TaskBase(BaseModel):
    """Base class for all task types."""

    id: str = Field(default_factory=generate_bead_id)
    project_id: UUID
    title: str
    description: str | None = None
    priority: Priority = Priority.P2
    status: TaskStatus = TaskStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # File references
    prompt_path: str | None = None
    output_path: str | None = None
    context_hash: str | None = None


class Epic(TaskBase):
    """Top-level container for a feature or initiative."""

    type: TaskType = TaskType.EPIC
    acceptance_criteria: list[str] = Field(default_factory=list)
    context: str | None = None  # RLM-processed context
    child_ids: list[str] = Field(default_factory=list)


class Task(TaskBase):
    """Mid-level work item assignable to a single worker."""

    type: TaskType = TaskType.TASK
    parent_id: str | None = None  # Epic ID
    worker_id: str | None = None
    attempts: int = 0
    max_attempts: int = 5

    # Execution tracking
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Graph metrics (cached from prioritization)
    pagerank_score: float = 0.0
    betweenness_score: float = 0.0
    on_critical_path: bool = False
    combined_priority: float = 0.0

    # Children
    subtask_ids: list[str] = Field(default_factory=list)


class Subtask(TaskBase):
    """Granular unit for complex task decomposition."""

    type: TaskType = TaskType.SUBTASK
    parent_id: str  # Task ID (required)
    worker_id: str | None = None
    attempts: int = 0
    max_attempts: int = 3


class Decision(BaseModel):
    """Human-in-the-loop decision point that blocks progress."""

    id: str = Field(default_factory=lambda: f"{generate_bead_id()}-d1")
    blocks_id: str  # Task ID waiting on this decision
    question: str
    context: str | None = None
    options: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    resolution: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Question(BaseModel):
    """Non-blocking clarification request."""

    id: str = Field(default_factory=lambda: f"{generate_bead_id()}-q1")
    related_id: str  # Task ID this relates to
    question: str
    urgency: str = "medium"  # low, medium, high
    default_answer: str | None = None  # What worker will assume if no answer
    answer: str | None = None
    answered_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Dependency(BaseModel):
    """Edge in the task dependency graph."""

    child_id: str  # Task that depends on another
    parent_id: str  # Task that must complete first
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Worker(BaseModel):
    """A coding agent worker (Claude Code, Aider, etc.)."""

    id: str = Field(default_factory=lambda: f"worker-{uuid4().hex[:8]}")
    name: str
    type: str  # claude-code, aider, codex, etc.
    status: WorkerStatus = WorkerStatus.OFFLINE
    current_task_id: str | None = None

    # Configuration
    command: str  # CLI command to invoke
    args: list[str] = Field(default_factory=list)
    prompt_flag: str = "-p"  # Flag to pass prompt
    working_dir: str | None = None
    timeout_seconds: int = 1800  # 30 minutes default
    env_vars: dict[str, str] = Field(default_factory=dict)

    # Stats
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_completion_seconds: float | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime | None = None
