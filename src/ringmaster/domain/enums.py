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
