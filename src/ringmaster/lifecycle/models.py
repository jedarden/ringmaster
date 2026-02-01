"""Task lifecycle models.

Defines the steps a task goes through based on project deployment model.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LifecycleStepName(str, Enum):
    """Names of possible lifecycle steps."""

    CREATED = "created"
    ASSIGNED = "assigned"
    PROMPT_BUILT = "prompt_built"
    EXECUTING = "executing"
    CHANGES_MADE = "changes_made"
    COMMITTED = "committed"
    PUSHED = "pushed"
    PR_CREATED = "pr_created"
    CI_RUNNING = "ci_running"
    CI_PASSED = "ci_passed"
    CI_FAILED = "ci_failed"
    MERGED = "merged"
    RELOADING = "reloading"
    HEALTH_CHECK = "health_check"
    DEPLOYING = "deploying"
    DEPLOY_SUCCESS = "deploy_success"
    DEPLOY_FAILED = "deploy_failed"
    ROLLED_BACK = "rolled_back"
    DONE = "done"
    FAILED = "failed"


class StepStatus(str, Enum):
    """Status of a lifecycle step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskLifecycleStep:
    """A single step in the task lifecycle."""

    name: LifecycleStepName
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskLifecycleStep":
        """Create from dictionary."""
        return cls(
            name=LifecycleStepName(data["name"]),
            status=StepStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {}),
            error=data.get("error"),
        )


class DeploymentModel(str, Enum):
    """How a project gets deployed after changes."""

    NONE = "none"  # Local dev, no deployment
    HOT_RELOAD = "hot_reload"  # Self-improvement with hot reload
    CI_CD = "ci_cd"  # Push triggers external CI/CD
    GITOPS = "gitops"  # ArgoCD/Flux watches repo
    MANUAL = "manual"  # Human deploys manually
    WEBHOOK = "webhook"  # Ringmaster calls deployment webhook


# Define which steps apply to each deployment model
STEPS_BY_MODEL: dict[DeploymentModel, list[LifecycleStepName]] = {
    DeploymentModel.NONE: [
        LifecycleStepName.CREATED,
        LifecycleStepName.ASSIGNED,
        LifecycleStepName.PROMPT_BUILT,
        LifecycleStepName.EXECUTING,
        LifecycleStepName.CHANGES_MADE,
        LifecycleStepName.COMMITTED,
        LifecycleStepName.DONE,
    ],
    DeploymentModel.HOT_RELOAD: [
        LifecycleStepName.CREATED,
        LifecycleStepName.ASSIGNED,
        LifecycleStepName.PROMPT_BUILT,
        LifecycleStepName.EXECUTING,
        LifecycleStepName.CHANGES_MADE,
        LifecycleStepName.COMMITTED,
        LifecycleStepName.MERGED,
        LifecycleStepName.RELOADING,
        LifecycleStepName.HEALTH_CHECK,
        LifecycleStepName.DONE,
    ],
    DeploymentModel.CI_CD: [
        LifecycleStepName.CREATED,
        LifecycleStepName.ASSIGNED,
        LifecycleStepName.PROMPT_BUILT,
        LifecycleStepName.EXECUTING,
        LifecycleStepName.CHANGES_MADE,
        LifecycleStepName.COMMITTED,
        LifecycleStepName.PUSHED,
        LifecycleStepName.PR_CREATED,
        LifecycleStepName.CI_RUNNING,
        LifecycleStepName.MERGED,
        LifecycleStepName.DONE,
    ],
    DeploymentModel.GITOPS: [
        LifecycleStepName.CREATED,
        LifecycleStepName.ASSIGNED,
        LifecycleStepName.PROMPT_BUILT,
        LifecycleStepName.EXECUTING,
        LifecycleStepName.CHANGES_MADE,
        LifecycleStepName.COMMITTED,
        LifecycleStepName.PUSHED,
        LifecycleStepName.PR_CREATED,
        LifecycleStepName.CI_RUNNING,
        LifecycleStepName.MERGED,
        LifecycleStepName.DEPLOYING,
        LifecycleStepName.HEALTH_CHECK,
        LifecycleStepName.DONE,
    ],
    DeploymentModel.MANUAL: [
        LifecycleStepName.CREATED,
        LifecycleStepName.ASSIGNED,
        LifecycleStepName.PROMPT_BUILT,
        LifecycleStepName.EXECUTING,
        LifecycleStepName.CHANGES_MADE,
        LifecycleStepName.COMMITTED,
        LifecycleStepName.PUSHED,
        LifecycleStepName.PR_CREATED,
        LifecycleStepName.DONE,
    ],
    DeploymentModel.WEBHOOK: [
        LifecycleStepName.CREATED,
        LifecycleStepName.ASSIGNED,
        LifecycleStepName.PROMPT_BUILT,
        LifecycleStepName.EXECUTING,
        LifecycleStepName.CHANGES_MADE,
        LifecycleStepName.COMMITTED,
        LifecycleStepName.PUSHED,
        LifecycleStepName.DEPLOYING,
        LifecycleStepName.HEALTH_CHECK,
        LifecycleStepName.DONE,
    ],
}


@dataclass
class TaskLifecycle:
    """Complete lifecycle for a task, based on project deployment model."""

    id: str
    task_id: str
    project_id: str
    deployment_model: DeploymentModel
    steps: list[TaskLifecycleStep]
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def for_model(
        cls,
        task_id: str,
        project_id: str,
        deployment_model: DeploymentModel,
        lifecycle_id: str | None = None,
    ) -> "TaskLifecycle":
        """Create lifecycle with appropriate steps for deployment model."""
        from ringmaster.domain.models import generate_id

        step_names = STEPS_BY_MODEL.get(deployment_model, STEPS_BY_MODEL[DeploymentModel.NONE])
        steps = [TaskLifecycleStep(name=name) for name in step_names]

        return cls(
            id=lifecycle_id or generate_id("lc"),
            task_id=task_id,
            project_id=project_id,
            deployment_model=deployment_model,
            steps=steps,
        )

    def get_step(self, name: LifecycleStepName) -> TaskLifecycleStep | None:
        """Get a step by name."""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def get_current_step(self) -> TaskLifecycleStep | None:
        """Get the currently active step (in_progress or first pending)."""
        for step in self.steps:
            if step.status == StepStatus.IN_PROGRESS:
                return step
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                return step
        return None

    def is_complete(self) -> bool:
        """Check if all steps are complete."""
        return all(
            step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for step in self.steps
        )

    def has_failed(self) -> bool:
        """Check if any step has failed."""
        return any(step.status == StepStatus.FAILED for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "deployment_model": self.deployment_model.value,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_complete": self.is_complete(),
            "has_failed": self.has_failed(),
            "current_step": self.get_current_step().name.value if self.get_current_step() else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskLifecycle":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            project_id=data["project_id"],
            deployment_model=DeploymentModel(data["deployment_model"]),
            steps=[TaskLifecycleStep.from_dict(s) for s in data["steps"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
