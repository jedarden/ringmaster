"""Event type definitions for the event bus."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events that can be broadcast."""

    # Task events
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_DELETED = "task.deleted"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Worker events
    WORKER_CREATED = "worker.created"
    WORKER_UPDATED = "worker.updated"
    WORKER_DELETED = "worker.deleted"
    WORKER_CONNECTED = "worker.connected"
    WORKER_DISCONNECTED = "worker.disconnected"

    # Project events
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"

    # Queue events
    QUEUE_UPDATED = "queue.updated"

    # Decision events
    DECISION_CREATED = "decision.created"
    DECISION_RESOLVED = "decision.resolved"

    # Question events
    QUESTION_CREATED = "question.created"
    QUESTION_ANSWERED = "question.answered"

    # Scheduler events
    SCHEDULER_STARTED = "scheduler.started"
    SCHEDULER_STOPPED = "scheduler.stopped"
    SCHEDULER_RELOAD = "scheduler.reload"

    # Chat/Message events
    MESSAGE_CREATED = "message.created"

    # Log events
    LOG_CREATED = "log.created"


class Event(BaseModel):
    """A broadcast event."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None  # For filtering by project

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "project_id": self.project_id,
        }
