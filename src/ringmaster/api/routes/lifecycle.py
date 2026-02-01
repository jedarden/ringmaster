"""Task lifecycle API routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database
from ringmaster.db.repositories import LifecycleRepository
from ringmaster.lifecycle import (
    DeploymentModel,
    LifecycleStepName,
    LifecycleTracker,
    TaskLifecycle,
)

router = APIRouter()


class LifecycleCreate(BaseModel):
    """Request body for creating a lifecycle."""

    task_id: str
    project_id: str
    deployment_model: str = "none"


class StepUpdate(BaseModel):
    """Request body for updating a step."""

    status: str  # pending, in_progress, completed, failed, skipped
    metadata: dict[str, Any] | None = None
    error: str | None = None


class LifecycleResponse(BaseModel):
    """Response model for lifecycle data."""

    id: str
    task_id: str
    project_id: str
    deployment_model: str
    steps: list[dict[str, Any]]
    created_at: str
    updated_at: str
    is_complete: bool
    has_failed: bool
    current_step: str | None


def _get_tracker(db: Database) -> LifecycleTracker:
    """Create a lifecycle tracker with repository."""
    repo = LifecycleRepository(db)
    return LifecycleTracker(repo)


@router.post("", response_model=LifecycleResponse)
async def create_lifecycle(
    data: LifecycleCreate,
    db: Annotated[Database, Depends(get_db)],
) -> dict[str, Any]:
    """Create a new task lifecycle.

    Creates a lifecycle with steps appropriate for the project's deployment model.
    """
    tracker = _get_tracker(db)

    # Check if lifecycle already exists
    existing = await tracker.get_lifecycle(data.task_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Lifecycle already exists for task {data.task_id}",
        )

    try:
        deployment_model = DeploymentModel(data.deployment_model)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid deployment model: {data.deployment_model}. "
            f"Valid options: {[m.value for m in DeploymentModel]}",
        )

    lifecycle = await tracker.create_lifecycle(
        task_id=data.task_id,
        project_id=data.project_id,
        deployment_model=deployment_model,
    )

    return lifecycle.to_dict()


@router.get("/{task_id}", response_model=LifecycleResponse)
async def get_lifecycle(
    task_id: str,
    db: Annotated[Database, Depends(get_db)],
) -> dict[str, Any]:
    """Get lifecycle for a task."""
    tracker = _get_tracker(db)
    lifecycle = await tracker.get_lifecycle(task_id)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.get("")
async def list_lifecycles(
    db: Annotated[Database, Depends(get_db)],
    project_id: str | None = None,
    deployment_model: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """List lifecycles with optional filters."""
    repo = LifecycleRepository(db)
    lifecycles = await repo.list_lifecycles(
        project_id=project_id,
        deployment_model=deployment_model,
        limit=limit,
        offset=offset,
    )
    return [lc.to_dict() for lc in lifecycles]


@router.post("/{task_id}/steps/{step_name}/start", response_model=LifecycleResponse)
async def start_step(
    task_id: str,
    step_name: str,
    db: Annotated[Database, Depends(get_db)],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a lifecycle step."""
    tracker = _get_tracker(db)

    try:
        step = LifecycleStepName(step_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step name: {step_name}",
        )

    lifecycle = await tracker.start_step(task_id, step, metadata)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.post("/{task_id}/steps/{step_name}/complete", response_model=LifecycleResponse)
async def complete_step(
    task_id: str,
    step_name: str,
    db: Annotated[Database, Depends(get_db)],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Complete a lifecycle step."""
    tracker = _get_tracker(db)

    try:
        step = LifecycleStepName(step_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step name: {step_name}",
        )

    lifecycle = await tracker.complete_step(task_id, step, metadata)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.post("/{task_id}/steps/{step_name}/fail", response_model=LifecycleResponse)
async def fail_step(
    task_id: str,
    step_name: str,
    error: str,
    db: Annotated[Database, Depends(get_db)],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark a lifecycle step as failed."""
    tracker = _get_tracker(db)

    try:
        step = LifecycleStepName(step_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step name: {step_name}",
        )

    lifecycle = await tracker.fail_step(task_id, step, error, metadata)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.post("/{task_id}/steps/{step_name}/skip", response_model=LifecycleResponse)
async def skip_step(
    task_id: str,
    step_name: str,
    db: Annotated[Database, Depends(get_db)],
    reason: str | None = None,
) -> dict[str, Any]:
    """Skip a lifecycle step."""
    tracker = _get_tracker(db)

    try:
        step = LifecycleStepName(step_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step name: {step_name}",
        )

    lifecycle = await tracker.skip_step(task_id, step, reason)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.post("/{task_id}/transition", response_model=LifecycleResponse)
async def transition_to_step(
    task_id: str,
    step_name: str,
    db: Annotated[Database, Depends(get_db)],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transition to a step, completing all previous steps."""
    tracker = _get_tracker(db)

    try:
        step = LifecycleStepName(step_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step name: {step_name}",
        )

    lifecycle = await tracker.transition_to(task_id, step, metadata)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.post("/{task_id}/done", response_model=LifecycleResponse)
async def mark_done(
    task_id: str,
    db: Annotated[Database, Depends(get_db)],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark lifecycle as done, completing all pending steps."""
    tracker = _get_tracker(db)
    lifecycle = await tracker.mark_done(task_id, metadata)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.post("/{task_id}/failed", response_model=LifecycleResponse)
async def mark_failed(
    task_id: str,
    error: str,
    db: Annotated[Database, Depends(get_db)],
    failed_step: str | None = None,
) -> dict[str, Any]:
    """Mark lifecycle as failed."""
    tracker = _get_tracker(db)

    step = None
    if failed_step:
        try:
            step = LifecycleStepName(failed_step)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid step name: {failed_step}",
            )

    lifecycle = await tracker.mark_failed(task_id, error, step)

    if not lifecycle:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return lifecycle.to_dict()


@router.delete("/{task_id}")
async def delete_lifecycle(
    task_id: str,
    db: Annotated[Database, Depends(get_db)],
) -> dict[str, str]:
    """Delete lifecycle for a task."""
    repo = LifecycleRepository(db)
    deleted = await repo.delete_lifecycle_by_task(task_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No lifecycle found for task {task_id}",
        )

    return {"status": "deleted", "task_id": task_id}


@router.get("/models/available")
async def get_deployment_models() -> list[dict[str, Any]]:
    """Get available deployment models and their steps."""
    from ringmaster.lifecycle.models import STEPS_BY_MODEL

    return [
        {
            "model": model.value,
            "steps": [step.value for step in steps],
        }
        for model, steps in STEPS_BY_MODEL.items()
    ]
