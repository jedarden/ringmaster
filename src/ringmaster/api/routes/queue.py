"""Queue API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, TaskRepository
from ringmaster.domain import Task
from ringmaster.queue import QueueManager

router = APIRouter()


class EnqueueRequest(BaseModel):
    """Request body for enqueuing a task."""

    task_id: str


class CompleteRequest(BaseModel):
    """Request body for completing a task."""

    task_id: str
    success: bool = True
    output_path: str | None = None


class RecalculateRequest(BaseModel):
    """Request body for recalculating priorities."""

    project_id: UUID


@router.get("/stats")
async def get_queue_stats(
    db: Annotated[Database, Depends(get_db)],
) -> dict:
    """Get current queue statistics."""
    manager = QueueManager(db)
    return await manager.get_queue_stats()


@router.get("/ready")
async def get_ready_tasks(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = None,
) -> list[Task]:
    """Get tasks ready for assignment."""
    repo = TaskRepository(db)
    return await repo.get_ready_tasks(project_id)


@router.post("/enqueue")
async def enqueue_task(
    db: Annotated[Database, Depends(get_db)],
    body: EnqueueRequest,
) -> dict:
    """Mark a task as ready for assignment."""
    manager = QueueManager(db)
    success = await manager.enqueue_task(body.task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Could not enqueue task. Check if it exists and dependencies are met.",
        )
    return {"status": "enqueued", "task_id": body.task_id}


@router.post("/complete")
async def complete_task(
    db: Annotated[Database, Depends(get_db)],
    body: CompleteRequest,
) -> dict:
    """Mark a task as complete or failed."""
    manager = QueueManager(db)
    await manager.complete_task(
        task_id=body.task_id,
        success=body.success,
        output_path=body.output_path,
    )
    return {
        "status": "completed" if body.success else "failed",
        "task_id": body.task_id,
    }


@router.post("/recalculate")
async def recalculate_priorities(
    db: Annotated[Database, Depends(get_db)],
    body: RecalculateRequest,
) -> dict:
    """Recalculate priorities for all tasks in a project."""
    manager = QueueManager(db)
    updated = await manager.recalculate_project_priorities(body.project_id)
    return {"status": "recalculated", "tasks_updated": updated}
