"""Enumerations for domain models."""

from enum import Enum


class Priority(str, Enum):
    """Task priority levels (P0 = critical, P4 = lowest)."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class TaskStatus(str, Enum):
    """Task lifecycle states."""

    DRAFT = "draft"
    READY = "ready"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    NEEDS_DECOMPOSITION = "needs_decomposition"  # Task too large, sent to bead-creator
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


class TaskType(str, Enum):
    """Types of work units."""

    EPIC = "epic"
    TASK = "task"
    SUBTASK = "subtask"
    DECISION = "decision"
    QUESTION = "question"


class WorkerStatus(str, Enum):
    """Worker availability states."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class LogLevel(str, Enum):
    """Log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogComponent(str, Enum):
    """System components that can emit logs."""

    API = "api"
    QUEUE = "queue"
    ENRICHER = "enricher"
    SCHEDULER = "scheduler"
    WORKER = "worker"
    RELOAD = "reload"
    CREATOR = "creator"


class ActionType(str, Enum):
    """Types of reversible actions for undo/redo."""

    # Task actions
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_STATUS_CHANGED = "task_status_changed"

    # Worker actions
    WORKER_ASSIGNED = "worker_assigned"
    WORKER_UNASSIGNED = "worker_unassigned"
    WORKER_CREATED = "worker_created"
    WORKER_UPDATED = "worker_updated"
    WORKER_DELETED = "worker_deleted"

    # Dependency actions
    DEPENDENCY_CREATED = "dependency_created"
    DEPENDENCY_DELETED = "dependency_deleted"

    # Project actions
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_DELETED = "project_deleted"

    # Bulk actions
    BULK_STATUS_CHANGED = "bulk_status_changed"
    BULK_DELETED = "bulk_deleted"


class EntityType(str, Enum):
    """Entity types that can have actions recorded."""

    TASK = "task"
    WORKER = "worker"
    PROJECT = "project"
    DEPENDENCY = "dependency"


class ActorType(str, Enum):
    """Actor types that can perform actions."""

    USER = "user"
    WORKER = "worker"
    SYSTEM = "system"
