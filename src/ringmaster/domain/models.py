"""Core domain models for Ringmaster.

Based on the Beads-inspired work unit hierarchy:
- Epic: Top-level container (feature, initiative)
- Task: Mid-level work item (single worker, single session)
- Subtask: Granular unit for complex tasks
- Decision: Human-in-the-loop blocking point
- Question: Non-blocking clarification request
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ringmaster.domain.enums import (
    ActionType,
    ActorType,
    EntityType,
    LogComponent,
    LogLevel,
    Priority,
    TaskStatus,
    TaskType,
    WorkerStatus,
)


def generate_bead_id() -> str:
    """Generate a Beads-style ID (bd-xxxx)."""
    return f"bd-{uuid4().hex[:8]}"


def utc_now() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class Project(BaseModel):
    """A project containing epics and tasks."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    repo_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskBase(BaseModel):
    """Base class for all task types."""

    id: str = Field(default_factory=generate_bead_id)
    project_id: UUID
    title: str
    description: str | None = None
    priority: Priority = Priority.P2
    status: TaskStatus = TaskStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

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

    # Required capabilities for worker matching
    # Workers must have ALL required capabilities to work on this task
    required_capabilities: list[str] = Field(default_factory=list)

    # Execution tracking
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Retry tracking
    # retry_after: When task can be retried (for exponential backoff)
    # last_failure_reason: Why the last attempt failed
    retry_after: datetime | None = None
    last_failure_reason: str | None = None

    # Blocking reason (when status=BLOCKED due to NEEDS_DECISION outcome)
    blocked_reason: str | None = None

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

    # Required capabilities for worker matching
    required_capabilities: list[str] = Field(default_factory=list)

    # Retry tracking
    retry_after: datetime | None = None
    last_failure_reason: str | None = None


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
    created_at: datetime = Field(default_factory=utc_now)


class Question(BaseModel):
    """Non-blocking clarification request."""

    id: str = Field(default_factory=lambda: f"{generate_bead_id()}-q1")
    related_id: str  # Task ID this relates to
    question: str
    urgency: str = "medium"  # low, medium, high
    default_answer: str | None = None  # What worker will assume if no answer
    answer: str | None = None
    answered_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Dependency(BaseModel):
    """Edge in the task dependency graph."""

    child_id: str  # Task that depends on another
    parent_id: str  # Task that must complete first
    created_at: datetime = Field(default_factory=utc_now)


class Worker(BaseModel):
    """A coding agent worker (Claude Code, Aider, etc.)."""

    id: str = Field(default_factory=lambda: f"worker-{uuid4().hex[:8]}")
    name: str
    type: str  # claude-code, aider, codex, etc.
    status: WorkerStatus = WorkerStatus.OFFLINE
    current_task_id: str | None = None

    # Capabilities for task-worker matching
    # e.g., ["python", "typescript", "security", "refactoring"]
    capabilities: list[str] = Field(default_factory=list)

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
    created_at: datetime = Field(default_factory=utc_now)
    last_active_at: datetime | None = None


class ChatMessage(BaseModel):
    """A message in the chat history for context enrichment."""

    id: int | None = None  # Set by database
    project_id: UUID
    task_id: str | None = None
    role: str  # user, assistant, system
    content: str
    media_type: str | None = None  # text, audio, image
    media_path: str | None = None
    token_count: int | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Summary(BaseModel):
    """An RLM-compressed summary of chat messages."""

    id: int | None = None  # Set by database
    project_id: UUID
    task_id: str | None = None
    message_range_start: int  # First message ID in range
    message_range_end: int  # Last message ID in range
    summary: str
    key_decisions: list[str] = Field(default_factory=list)
    token_count: int | None = None
    created_at: datetime = Field(default_factory=utc_now)


class LogEntry(BaseModel):
    """A structured log entry for observability."""

    id: int | None = None  # Set by database
    timestamp: datetime = Field(default_factory=utc_now)
    level: LogLevel = LogLevel.INFO
    component: LogComponent
    message: str
    task_id: str | None = None
    worker_id: str | None = None
    project_id: UUID | None = None
    data: dict[str, Any] | None = None  # Additional context


class Action(BaseModel):
    """A reversible action for undo/redo functionality.

    Records the before/after state to enable reverting changes.
    See docs/07-user-experience.md for the reversibility UX principle.
    """

    id: int | None = None  # Set by database
    action_type: ActionType
    entity_type: EntityType
    entity_id: str

    # State snapshots (JSON) for undo/redo
    previous_state: dict[str, Any] | None = None  # State before action (null for creates)
    new_state: dict[str, Any] | None = None  # State after action (null for deletes)

    # Scope
    project_id: UUID | None = None

    # Undo tracking
    undone: bool = False
    undone_at: datetime | None = None

    # Attribution
    actor_type: ActorType = ActorType.USER
    actor_id: str | None = None  # Worker ID if actor_type='worker'

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)

    def description(self) -> str:
        """Generate a human-readable description of the action."""
        action_descriptions = {
            ActionType.TASK_CREATED: "Task created",
            ActionType.TASK_UPDATED: "Task updated",
            ActionType.TASK_DELETED: "Task deleted",
            ActionType.TASK_STATUS_CHANGED: "Task status changed",
            ActionType.WORKER_ASSIGNED: "Worker assigned",
            ActionType.WORKER_UNASSIGNED: "Worker unassigned",
            ActionType.WORKER_CREATED: "Worker created",
            ActionType.WORKER_UPDATED: "Worker updated",
            ActionType.WORKER_DELETED: "Worker deleted",
            ActionType.DEPENDENCY_CREATED: "Dependency created",
            ActionType.DEPENDENCY_DELETED: "Dependency deleted",
            ActionType.PROJECT_CREATED: "Project created",
            ActionType.PROJECT_UPDATED: "Project updated",
            ActionType.PROJECT_DELETED: "Project deleted",
            ActionType.BULK_STATUS_CHANGED: "Bulk status change",
            ActionType.BULK_DELETED: "Bulk delete",
        }
        return action_descriptions.get(self.action_type, str(self.action_type))


class ContextAssemblyLog(BaseModel):
    """Log entry for context assembly observability.

    Per docs/04-context-enrichment.md "Observability" section:
    Tracks what context is being assembled for each task to enable
    debugging, analysis, and improvement of the enrichment pipeline.
    """

    id: int | None = None

    # Task and project reference
    task_id: str
    project_id: UUID

    # Assembly metrics
    sources_queried: list[str] = Field(default_factory=list)  # Source names queried
    candidates_found: int = 0  # Total candidate items found
    items_included: int = 0  # Items that made it into final context
    tokens_used: int = 0  # Actual tokens used
    tokens_budget: int = 0  # Token budget for this assembly

    # Compression tracking
    compression_applied: list[str] = Field(default_factory=list)  # Sources that were compressed
    compression_ratio: float = 1.0  # Overall compression ratio (0-1, 1 = no compression)

    # Stage tracking
    stages_applied: list[str] = Field(default_factory=list)  # Stages that contributed content

    # Performance
    assembly_time_ms: int = 0  # Time to assemble context in milliseconds

    # Context hash for deduplication detection
    context_hash: str | None = None  # SHA256 prefix of assembled context

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
