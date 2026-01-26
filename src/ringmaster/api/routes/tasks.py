"""Task API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, TaskRepository
from ringmaster.domain import (
    Dependency,
    Epic,
    Priority,
    Subtask,
    Task,
    TaskStatus,
    TaskType,
)

router = APIRouter()


class TaskCreate(BaseModel):
    """Request body for creating a task."""

    project_id: UUID
    title: str
    description: str | None = None
    priority: Priority = Priority.P2
    parent_id: str | None = None
    task_type: TaskType = TaskType.TASK


class EpicCreate(BaseModel):
    """Request body for creating an epic."""

    project_id: UUID
    title: str
    description: str | None = None
    priority: Priority = Priority.P2
    acceptance_criteria: list[str] = []


class TaskUpdate(BaseModel):
    """Request body for updating a task."""

    title: str | None = None
    description: str | None = None
    priority: Priority | None = None
    status: TaskStatus | None = None


class DependencyCreate(BaseModel):
    """Request body for creating a dependency."""

    parent_id: str  # Task that must complete first


@router.get("")
async def list_tasks(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = None,
    parent_id: str | None = None,
    status: TaskStatus | None = None,
    task_type: TaskType | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Task | Epic | Subtask]:
    """List tasks with optional filters."""
    repo = TaskRepository(db)
    return await repo.list_tasks(
        project_id=project_id,
        parent_id=parent_id,
        status=status,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201)
async def create_task(
    db: Annotated[Database, Depends(get_db)],
    body: TaskCreate,
) -> Task | Subtask:
    """Create a new task or subtask."""
    repo = TaskRepository(db)

    if body.task_type == TaskType.SUBTASK:
        if not body.parent_id:
            raise HTTPException(status_code=400, detail="Subtask requires parent_id")
        task = Subtask(
            project_id=body.project_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
            parent_id=body.parent_id,
        )
    else:
        task = Task(
            project_id=body.project_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
            parent_id=body.parent_id,
        )

    return await repo.create_task(task)


@router.post("/epics", status_code=201)
async def create_epic(
    db: Annotated[Database, Depends(get_db)],
    body: EpicCreate,
) -> Epic:
    """Create a new epic."""
    repo = TaskRepository(db)
    epic = Epic(
        project_id=body.project_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        acceptance_criteria=body.acceptance_criteria,
    )
    return await repo.create_task(epic)


@router.get("/{task_id}")
async def get_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
) -> Task | Epic | Subtask:
    """Get a task by ID."""
    repo = TaskRepository(db)
    task = await repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}")
async def update_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    body: TaskUpdate,
) -> Task | Epic | Subtask:
    """Update a task."""
    repo = TaskRepository(db)
    task = await repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.priority is not None:
        task.priority = body.priority
    if body.status is not None:
        task.status = body.status

    return await repo.update_task(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
) -> None:
    """Delete a task."""
    repo = TaskRepository(db)
    deleted = await repo.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")


@router.get("/{task_id}/dependencies")
async def get_task_dependencies(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
) -> list[Dependency]:
    """Get dependencies for a task."""
    repo = TaskRepository(db)
    return await repo.get_dependencies(task_id)


@router.post("/{task_id}/dependencies", status_code=201)
async def add_task_dependency(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    body: DependencyCreate,
) -> Dependency:
    """Add a dependency to a task."""
    repo = TaskRepository(db)

    # Verify both tasks exist
    child = await repo.get_task(task_id)
    if not child:
        raise HTTPException(status_code=404, detail="Task not found")

    parent = await repo.get_task(body.parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent task not found")

    dependency = Dependency(child_id=task_id, parent_id=body.parent_id)
    return await repo.add_dependency(dependency)


@router.get("/{task_id}/dependents")
async def get_task_dependents(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
) -> list[Dependency]:
    """Get tasks that depend on this task."""
    repo = TaskRepository(db)
    return await repo.get_dependents(task_id)
