"""Lifecycle tracker for managing task lifecycle state transitions."""

import logging
from datetime import UTC, datetime
from typing import Any

from ringmaster.lifecycle.models import (
    DeploymentModel,
    LifecycleStepName,
    StepStatus,
    TaskLifecycle,
    TaskLifecycleStep,
)

logger = logging.getLogger(__name__)


class LifecycleTracker:
    """Tracks and updates task lifecycle state.

    This class manages lifecycle transitions and persists state to the database.
    It's designed to be called from various points in the task execution flow.
    """

    def __init__(self, repository: Any):
        """Initialize with a lifecycle repository.

        Args:
            repository: LifecycleRepository instance for persistence.
        """
        self.repository = repository

    async def create_lifecycle(
        self,
        task_id: str,
        project_id: str,
        deployment_model: DeploymentModel | str,
    ) -> TaskLifecycle:
        """Create a new lifecycle for a task.

        Args:
            task_id: The task ID.
            project_id: The project ID.
            deployment_model: The deployment model (determines steps).

        Returns:
            The created TaskLifecycle.
        """
        if isinstance(deployment_model, str):
            deployment_model = DeploymentModel(deployment_model)

        lifecycle = TaskLifecycle.for_model(
            task_id=task_id,
            project_id=project_id,
            deployment_model=deployment_model,
        )

        # Mark created step as completed
        created_step = lifecycle.get_step(LifecycleStepName.CREATED)
        if created_step:
            now = datetime.now(UTC)
            created_step.status = StepStatus.COMPLETED
            created_step.started_at = now
            created_step.completed_at = now

        await self.repository.create_lifecycle(lifecycle)
        logger.info(f"Created lifecycle {lifecycle.id} for task {task_id}")

        return lifecycle

    async def get_lifecycle(self, task_id: str) -> TaskLifecycle | None:
        """Get lifecycle for a task.

        Args:
            task_id: The task ID.

        Returns:
            TaskLifecycle or None if not found.
        """
        return await self.repository.get_lifecycle_by_task(task_id)

    async def start_step(
        self,
        task_id: str,
        step_name: LifecycleStepName,
        metadata: dict[str, Any] | None = None,
    ) -> TaskLifecycle | None:
        """Start a lifecycle step.

        Args:
            task_id: The task ID.
            step_name: The step to start.
            metadata: Optional metadata for the step.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            logger.warning(f"No lifecycle found for task {task_id}")
            return None

        step = lifecycle.get_step(step_name)
        if not step:
            logger.warning(f"Step {step_name} not in lifecycle for task {task_id}")
            return lifecycle

        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.now(UTC)
        if metadata:
            step.metadata.update(metadata)

        lifecycle.updated_at = datetime.now(UTC)
        await self.repository.update_lifecycle(lifecycle)

        logger.debug(f"Started step {step_name} for task {task_id}")
        return lifecycle

    async def complete_step(
        self,
        task_id: str,
        step_name: LifecycleStepName,
        metadata: dict[str, Any] | None = None,
    ) -> TaskLifecycle | None:
        """Complete a lifecycle step.

        Args:
            task_id: The task ID.
            step_name: The step to complete.
            metadata: Optional metadata for the step.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            logger.warning(f"No lifecycle found for task {task_id}")
            return None

        step = lifecycle.get_step(step_name)
        if not step:
            logger.warning(f"Step {step_name} not in lifecycle for task {task_id}")
            return lifecycle

        now = datetime.now(UTC)
        step.status = StepStatus.COMPLETED
        step.completed_at = now
        if not step.started_at:
            step.started_at = now
        if metadata:
            step.metadata.update(metadata)

        lifecycle.updated_at = now
        await self.repository.update_lifecycle(lifecycle)

        logger.debug(f"Completed step {step_name} for task {task_id}")
        return lifecycle

    async def fail_step(
        self,
        task_id: str,
        step_name: LifecycleStepName,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> TaskLifecycle | None:
        """Mark a lifecycle step as failed.

        Args:
            task_id: The task ID.
            step_name: The step that failed.
            error: Error message.
            metadata: Optional metadata for the step.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            logger.warning(f"No lifecycle found for task {task_id}")
            return None

        step = lifecycle.get_step(step_name)
        if not step:
            logger.warning(f"Step {step_name} not in lifecycle for task {task_id}")
            return lifecycle

        now = datetime.now(UTC)
        step.status = StepStatus.FAILED
        step.completed_at = now
        step.error = error
        if not step.started_at:
            step.started_at = now
        if metadata:
            step.metadata.update(metadata)

        lifecycle.updated_at = now
        await self.repository.update_lifecycle(lifecycle)

        logger.warning(f"Step {step_name} failed for task {task_id}: {error}")
        return lifecycle

    async def skip_step(
        self,
        task_id: str,
        step_name: LifecycleStepName,
        reason: str | None = None,
    ) -> TaskLifecycle | None:
        """Skip a lifecycle step.

        Args:
            task_id: The task ID.
            step_name: The step to skip.
            reason: Optional reason for skipping.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            logger.warning(f"No lifecycle found for task {task_id}")
            return None

        step = lifecycle.get_step(step_name)
        if not step:
            logger.warning(f"Step {step_name} not in lifecycle for task {task_id}")
            return lifecycle

        now = datetime.now(UTC)
        step.status = StepStatus.SKIPPED
        step.completed_at = now
        if reason:
            step.metadata["skip_reason"] = reason

        lifecycle.updated_at = now
        await self.repository.update_lifecycle(lifecycle)

        logger.debug(f"Skipped step {step_name} for task {task_id}: {reason}")
        return lifecycle

    async def update_step_metadata(
        self,
        task_id: str,
        step_name: LifecycleStepName,
        metadata: dict[str, Any],
    ) -> TaskLifecycle | None:
        """Update metadata for a step without changing status.

        Args:
            task_id: The task ID.
            step_name: The step to update.
            metadata: Metadata to merge.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            return None

        step = lifecycle.get_step(step_name)
        if not step:
            return lifecycle

        step.metadata.update(metadata)
        lifecycle.updated_at = datetime.now(UTC)
        await self.repository.update_lifecycle(lifecycle)

        return lifecycle

    async def transition_to(
        self,
        task_id: str,
        step_name: LifecycleStepName,
        metadata: dict[str, Any] | None = None,
    ) -> TaskLifecycle | None:
        """Transition to a step, completing all previous steps.

        This is useful when steps happen quickly and we want to mark
        multiple steps as complete in one call.

        Args:
            task_id: The task ID.
            step_name: The step to transition to.
            metadata: Optional metadata for the target step.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            logger.warning(f"No lifecycle found for task {task_id}")
            return None

        now = datetime.now(UTC)
        target_reached = False

        for step in lifecycle.steps:
            if step.name == step_name:
                target_reached = True
                step.status = StepStatus.IN_PROGRESS
                step.started_at = now
                if metadata:
                    step.metadata.update(metadata)
                break
            elif step.status == StepStatus.PENDING:
                # Complete all pending steps before target
                step.status = StepStatus.COMPLETED
                step.started_at = step.started_at or now
                step.completed_at = now

        if not target_reached:
            logger.warning(f"Step {step_name} not found in lifecycle for task {task_id}")

        lifecycle.updated_at = now
        await self.repository.update_lifecycle(lifecycle)

        return lifecycle

    async def mark_done(
        self,
        task_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TaskLifecycle | None:
        """Mark lifecycle as done, completing all pending steps.

        Args:
            task_id: The task ID.
            metadata: Optional metadata for the done step.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            return None

        now = datetime.now(UTC)

        for step in lifecycle.steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.COMPLETED
                step.started_at = step.started_at or now
                step.completed_at = now
            elif step.status == StepStatus.IN_PROGRESS:
                step.status = StepStatus.COMPLETED
                step.completed_at = now

        # Set done step metadata if provided
        done_step = lifecycle.get_step(LifecycleStepName.DONE)
        if done_step and metadata:
            done_step.metadata.update(metadata)

        lifecycle.updated_at = now
        await self.repository.update_lifecycle(lifecycle)

        logger.info(f"Lifecycle marked done for task {task_id}")
        return lifecycle

    async def mark_failed(
        self,
        task_id: str,
        error: str,
        failed_step: LifecycleStepName | None = None,
    ) -> TaskLifecycle | None:
        """Mark lifecycle as failed.

        Args:
            task_id: The task ID.
            error: Error message.
            failed_step: Optional specific step that failed.

        Returns:
            Updated TaskLifecycle or None if not found.
        """
        lifecycle = await self.repository.get_lifecycle_by_task(task_id)
        if not lifecycle:
            return None

        now = datetime.now(UTC)

        # If specific step provided, fail that step
        if failed_step:
            step = lifecycle.get_step(failed_step)
            if step:
                step.status = StepStatus.FAILED
                step.completed_at = now
                step.error = error

        # Mark any in-progress step as failed
        for step in lifecycle.steps:
            if step.status == StepStatus.IN_PROGRESS:
                step.status = StepStatus.FAILED
                step.completed_at = now
                step.error = step.error or error

        # Add/update failed step if it exists
        failed = lifecycle.get_step(LifecycleStepName.FAILED)
        if failed:
            failed.status = StepStatus.COMPLETED
            failed.started_at = now
            failed.completed_at = now
            failed.metadata["error"] = error

        lifecycle.updated_at = now
        await self.repository.update_lifecycle(lifecycle)

        logger.warning(f"Lifecycle marked failed for task {task_id}: {error}")
        return lifecycle
