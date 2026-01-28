"""Queue API routes."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, TaskRepository
from ringmaster.domain import Task
from ringmaster.queue import QueueManager

logger = logging.getLogger(__name__)
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
    logger.info("Getting queue statistics")
    manager = QueueManager(db)
    stats = await manager.get_queue_stats()
    logger.info(f"Queue stats retrieved: {stats}")
    return stats


@router.get("/ready")
async def get_ready_tasks(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = None,
) -> list[Task]:
    """Get tasks ready for assignment."""
    if project_id:
        logger.info(f"Getting ready tasks for project {project_id}")
    else:
        logger.info("Getting ready tasks for all projects")
    repo = TaskRepository(db)
    tasks = await repo.get_ready_tasks(project_id)
    logger.info(f"Found {len(tasks)} ready tasks")
    return tasks


@router.post("/enqueue")
async def enqueue_task(
    db: Annotated[Database, Depends(get_db)],
    body: EnqueueRequest,
) -> dict:
    """Mark a task as ready for assignment."""
    logger.info(f"Enqueuing task {body.task_id}")
    manager = QueueManager(db)
    success = await manager.enqueue_task(body.task_id)
    if not success:
        logger.warning(f"Failed to enqueue task {body.task_id}: dependencies not met or task not found")
        raise HTTPException(
            status_code=400,
            detail="Could not enqueue task. Check if it exists and dependencies are met.",
        )
    logger.info(f"Successfully enqueued task {body.task_id}")
    return {"status": "enqueued", "task_id": body.task_id}


@router.post("/complete")
async def complete_task(
    db: Annotated[Database, Depends(get_db)],
    body: CompleteRequest,
) -> dict:
    """Mark a task as complete or failed."""
    status_str = "completed" if body.success else "failed"
    logger.info(f"Marking task {body.task_id} as {status_str}")
    manager = QueueManager(db)
    await manager.complete_task(
        task_id=body.task_id,
        success=body.success,
        output_path=body.output_path,
    )
    logger.info(f"Task {body.task_id} successfully marked as {status_str}")
    return {
        "status": status_str,
        "task_id": body.task_id,
    }


@router.post("/recalculate")
async def recalculate_priorities(
    db: Annotated[Database, Depends(get_db)],
    body: RecalculateRequest,
) -> dict:
    """Recalculate priorities for all tasks in a project."""
    logger.info(f"Recalculating priorities for project {body.project_id}")
    manager = QueueManager(db)
    updated = await manager.recalculate_project_priorities(body.project_id)
    logger.info(f"Recalculated priorities for project {body.project_id}: {updated} tasks updated")
    return {"status": "recalculated", "tasks_updated": updated}
