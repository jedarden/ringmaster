"""Task API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, TaskRepository, WorkerRepository
from ringmaster.domain import (
    Dependency,
    Epic,
    Priority,
    Subtask,
    Task,
    TaskStatus,
    TaskType,
    WorkerStatus,
)
from ringmaster.events import EventType, event_bus

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


class TaskAssign(BaseModel):
    """Request body for assigning a task to a worker."""

    worker_id: str | None = None  # None to unassign


class BulkUpdateRequest(BaseModel):
    """Request body for bulk task updates."""

    task_ids: list[str]
    status: TaskStatus | None = None
    priority: Priority | None = None
    worker_id: str | None = None  # For bulk assignment (None = no change, empty string = unassign)
    unassign: bool = False  # If True, unassign all selected tasks


class BulkUpdateResponse(BaseModel):
    """Response for bulk task updates."""

    updated: int
    failed: int
    errors: list[str]


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

    created = await repo.create_task(task)

    # Emit event
    await event_bus.emit(
        EventType.TASK_CREATED,
        data={"task_id": created.id, "title": created.title, "type": created.type.value},
        project_id=str(body.project_id),
    )

    return created


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
    created = await repo.create_task(epic)

    # Emit event
    await event_bus.emit(
        EventType.TASK_CREATED,
        data={"task_id": created.id, "title": created.title, "type": "epic"},
        project_id=str(body.project_id),
    )

    return created


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

    updated = await repo.update_task(task)

    # Emit event
    await event_bus.emit(
        EventType.TASK_UPDATED,
        data={"task_id": updated.id, "status": updated.status.value},
        project_id=str(updated.project_id),
    )

    return updated


@router.post("/{task_id}/assign")
async def assign_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    body: TaskAssign,
) -> Task | Subtask:
    """Assign a task to a worker or unassign it."""
    task_repo = TaskRepository(db)
    worker_repo = WorkerRepository(db)

    task = await task_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Only tasks and subtasks can be assigned (not epics)
    if task.type == TaskType.EPIC:
        raise HTTPException(status_code=400, detail="Epics cannot be assigned to workers")

    if body.worker_id:
        # Assigning to a worker
        worker = await worker_repo.get(body.worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        # Check if worker is available
        if worker.status == WorkerStatus.OFFLINE:
            raise HTTPException(status_code=400, detail="Worker is offline")

        # If worker is already busy with another task, don't allow
        if worker.status == WorkerStatus.BUSY and worker.current_task_id != task_id:
            raise HTTPException(
                status_code=400,
                detail=f"Worker is busy with task {worker.current_task_id}",
            )

        # Update task
        task.worker_id = body.worker_id
        task.status = TaskStatus.ASSIGNED

        # Update worker to busy
        worker.status = WorkerStatus.BUSY
        worker.current_task_id = task_id
        await worker_repo.update(worker)
    else:
        # Unassigning from worker
        old_worker_id = task.worker_id
        task.worker_id = None
        task.status = TaskStatus.READY

        # If there was a worker, mark them idle
        if old_worker_id:
            worker = await worker_repo.get(old_worker_id)
            if worker and worker.current_task_id == task_id:
                worker.status = WorkerStatus.IDLE
                worker.current_task_id = None
                await worker_repo.update(worker)

    updated = await task_repo.update_task(task)

    # Emit event
    await event_bus.emit(
        EventType.TASK_UPDATED,
        data={
            "task_id": updated.id,
            "worker_id": body.worker_id,
            "status": updated.status.value,
            "action": "assigned" if body.worker_id else "unassigned",
        },
        project_id=str(updated.project_id),
    )

    return updated


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
) -> None:
    """Delete a task."""
    repo = TaskRepository(db)

    # Get task before deleting to get project_id for event
    task = await repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    deleted = await repo.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")

    # Emit event
    await event_bus.emit(
        EventType.TASK_DELETED,
        data={"task_id": task_id},
        project_id=str(task.project_id),
    )


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


@router.delete("/{task_id}/dependencies/{parent_id}")
async def remove_task_dependency(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    parent_id: str,
) -> dict[str, bool]:
    """Remove a dependency from a task."""
    repo = TaskRepository(db)

    # Verify the task exists
    task = await repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    removed = await repo.remove_dependency(child_id=task_id, parent_id=parent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Dependency not found")

    return {"removed": True}


@router.post("/bulk-update")
async def bulk_update_tasks(
    db: Annotated[Database, Depends(get_db)],
    body: BulkUpdateRequest,
) -> BulkUpdateResponse:
    """Bulk update multiple tasks."""
    task_repo = TaskRepository(db)
    worker_repo = WorkerRepository(db)

    updated = 0
    failed = 0
    errors: list[str] = []

    # If assigning to a worker, validate the worker exists and is available
    target_worker = None
    if body.worker_id:
        target_worker = await worker_repo.get(body.worker_id)
        if not target_worker:
            return BulkUpdateResponse(
                updated=0,
                failed=len(body.task_ids),
                errors=[f"Worker {body.worker_id} not found"],
            )
        if target_worker.status == WorkerStatus.OFFLINE:
            return BulkUpdateResponse(
                updated=0,
                failed=len(body.task_ids),
                errors=["Worker is offline"],
            )

    for task_id in body.task_ids:
        try:
            task = await task_repo.get_task(task_id)
            if not task:
                errors.append(f"Task {task_id} not found")
                failed += 1
                continue

            # Epics cannot be assigned
            if task.type == TaskType.EPIC and (body.worker_id or body.unassign):
                errors.append(f"Epic {task_id} cannot be assigned to workers")
                failed += 1
                continue

            changed = False

            # Update status if provided
            if body.status is not None and task.status != body.status:
                task.status = body.status
                changed = True

            # Update priority if provided
            if body.priority is not None and task.priority != body.priority:
                task.priority = body.priority
                changed = True

            # Handle assignment/unassignment
            if body.unassign and hasattr(task, "worker_id") and task.worker_id:
                old_worker_id = task.worker_id
                task.worker_id = None
                if task.status == TaskStatus.ASSIGNED:
                    task.status = TaskStatus.READY
                changed = True

                # Mark old worker as idle
                old_worker = await worker_repo.get(old_worker_id)
                if old_worker and old_worker.current_task_id == task_id:
                    old_worker.status = WorkerStatus.IDLE
                    old_worker.current_task_id = None
                    await worker_repo.update(old_worker)

            elif body.worker_id and hasattr(task, "worker_id"):
                # Check if worker is busy with another task
                if (
                    target_worker
                    and target_worker.status == WorkerStatus.BUSY
                    and target_worker.current_task_id != task_id
                ):
                    errors.append(
                        f"Worker busy, cannot assign task {task_id}"
                    )
                    failed += 1
                    continue

                task.worker_id = body.worker_id
                task.status = TaskStatus.ASSIGNED
                changed = True

            if changed:
                await task_repo.update_task(task)
                updated += 1

                # Emit event
                await event_bus.emit(
                    EventType.TASK_UPDATED,
                    data={"task_id": task.id, "status": task.status.value, "bulk": True},
                    project_id=str(task.project_id),
                )
            else:
                # No changes needed
                updated += 1

        except Exception as e:
            errors.append(f"Error updating {task_id}: {str(e)}")
            failed += 1

    return BulkUpdateResponse(updated=updated, failed=failed, errors=errors)


class BulkDeleteRequest(BaseModel):
    """Request body for bulk task deletion."""

    task_ids: list[str]


class ResubmitRequest(BaseModel):
    """Request body for resubmitting a task for decomposition."""

    reason: str  # Why the worker is resubmitting the task


class ResubmitResponse(BaseModel):
    """Response for task resubmission."""

    task_id: str
    status: str  # The new status (needs_decomposition)
    reason: str
    decomposed: bool  # Whether the task was immediately decomposed
    subtasks_created: int  # Number of subtasks created (if decomposed)


@router.post("/bulk-delete")
async def bulk_delete_tasks(
    db: Annotated[Database, Depends(get_db)],
    body: BulkDeleteRequest,
) -> BulkUpdateResponse:
    """Bulk delete multiple tasks."""
    task_repo = TaskRepository(db)

    deleted = 0
    failed = 0
    errors: list[str] = []

    for task_id in body.task_ids:
        try:
            task = await task_repo.get_task(task_id)
            if not task:
                errors.append(f"Task {task_id} not found")
                failed += 1
                continue

            project_id = str(task.project_id)
            success = await task_repo.delete_task(task_id)
            if success:
                deleted += 1
                # Emit event
                await event_bus.emit(
                    EventType.TASK_DELETED,
                    data={"task_id": task_id, "bulk": True},
                    project_id=project_id,
                )
            else:
                errors.append(f"Failed to delete {task_id}")
                failed += 1

        except Exception as e:
            errors.append(f"Error deleting {task_id}: {str(e)}")
            failed += 1

    return BulkUpdateResponse(updated=deleted, failed=failed, errors=errors)


@router.post("/{task_id}/resubmit")
async def resubmit_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    body: ResubmitRequest,
) -> ResubmitResponse:
    """Resubmit a task for decomposition.

    Workers can call this when they determine a task is too large to
    complete in a single session. The task will be marked as
    NEEDS_DECOMPOSITION and sent to the BeadCreator for breakdown.

    Args:
        task_id: The task ID to resubmit.
        body: Reason for resubmission.

    Returns:
        ResubmitResponse with decomposition results.
    """
    from ringmaster.creator.decomposer import decompose_candidate
    from ringmaster.creator.parser import TaskCandidate, detect_action_type, extract_target

    task_repo = TaskRepository(db)
    worker_repo = WorkerRepository(db)

    task = await task_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Only tasks (not epics or subtasks) can be resubmitted
    if task.type == TaskType.EPIC:
        raise HTTPException(status_code=400, detail="Epics cannot be resubmitted")
    if task.type == TaskType.SUBTASK:
        raise HTTPException(status_code=400, detail="Subtasks cannot be resubmitted")

    # Get the worker if assigned
    worker = None
    if hasattr(task, "worker_id") and task.worker_id:
        worker = await worker_repo.get(task.worker_id)

    # Mark task as needs decomposition
    old_status = task.status
    task.status = TaskStatus.NEEDS_DECOMPOSITION

    # Store resubmit reason in description
    if body.reason:
        task.description = (task.description or "") + f"\n\n[Resubmitted: {body.reason}]"

    # Unassign from worker
    if hasattr(task, "worker_id") and task.worker_id:
        task.worker_id = None

    await task_repo.update_task(task)

    # Mark worker as idle if it was assigned
    if worker:
        worker.status = WorkerStatus.IDLE
        worker.current_task_id = None
        await worker_repo.update(worker)

    # Emit resubmitted event
    await event_bus.emit(
        EventType.TASK_RESUBMITTED,
        data={
            "task_id": task_id,
            "previous_status": old_status.value,
            "reason": body.reason,
        },
        project_id=str(task.project_id),
    )

    # Try to decompose immediately
    decomposed = False
    subtasks_created = 0

    # Create a TaskCandidate from the task description
    text = f"{task.title}. {task.description or ''}"
    action_type, _confidence = detect_action_type(text)
    target = extract_target(text, action_type)

    candidate = TaskCandidate(
        raw_text=text,
        action_type=action_type,
        target=target or task.title[:50],
        order_hint=0,
        confidence=0.8,
    )

    decomp = decompose_candidate(candidate)

    if decomp.should_decompose and decomp.subtasks:
        # Create subtasks
        subtask_ids: list[str] = []
        for subtask_candidate in decomp.subtasks:
            subtask = Subtask(
                project_id=task.project_id,
                title=subtask_candidate.to_title(),
                description=subtask_candidate.raw_text,
                priority=task.priority,
                parent_id=task.id,
                status=TaskStatus.READY,
            )
            created_subtask = await task_repo.create_task(subtask)
            subtask_ids.append(created_subtask.id)

            await event_bus.emit(
                EventType.TASK_CREATED,
                data={
                    "task_id": created_subtask.id,
                    "title": created_subtask.title,
                    "type": "subtask",
                    "parent_id": task.id,
                    "from_resubmission": True,
                },
                project_id=str(task.project_id),
            )

        # Update task with subtask IDs and set status back to READY
        task.subtask_ids = subtask_ids
        task.status = TaskStatus.READY
        await task_repo.update_task(task)

        decomposed = True
        subtasks_created = len(subtask_ids)

    return ResubmitResponse(
        task_id=task_id,
        status=task.status.value,
        reason=body.reason,
        decomposed=decomposed,
        subtasks_created=subtasks_created,
    )


class RoutingSignals(BaseModel):
    """Signals used to determine task complexity."""

    file_count: int
    dependency_count: int
    description_length: int
    simple_keyword_matches: int
    complex_keyword_matches: int
    is_epic: bool
    is_subtask: bool
    is_critical: bool
    raw_score: int


class RoutingRecommendation(BaseModel):
    """Model routing recommendation for a task."""

    task_id: str
    complexity: str  # simple, moderate, complex
    tier: str  # fast, balanced, powerful
    reasoning: str
    suggested_models: list[str]
    signals: RoutingSignals


@router.get("/{task_id}/routing")
async def get_routing_recommendation(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    worker_type: str | None = Query(
        None, description="Worker type for specific model recommendation"
    ),
) -> RoutingRecommendation:
    """Get model routing recommendation for a task.

    Analyzes task complexity and suggests appropriate model tier.
    Uses deterministic heuristics based on file count, keywords,
    task type, and priority.

    Args:
        task_id: The task ID to analyze.
        worker_type: Optional worker type (claude-code, aider, codex, goose)
            for specific model recommendations.

    Returns:
        RoutingRecommendation with complexity analysis and model suggestions.
    """
    from ringmaster.queue.routing import (
        get_model_for_worker_type,
        select_model_for_task,
    )

    task_repo = TaskRepository(db)

    task = await task_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get routing decision
    result = select_model_for_task(task)

    # If worker type specified, get specific model
    suggested_models = result.suggested_models.copy()
    if worker_type:
        specific_model = get_model_for_worker_type(result.tier, worker_type)
        if specific_model:
            # Put the specific model first
            suggested_models = [specific_model] + [
                m for m in suggested_models if m != specific_model
            ]

    return RoutingRecommendation(
        task_id=task_id,
        complexity=result.complexity.value,
        tier=result.tier.value,
        reasoning=result.reasoning,
        suggested_models=suggested_models,
        signals=RoutingSignals(
            file_count=result.signals.file_count,
            dependency_count=result.signals.dependency_count,
            description_length=result.signals.description_length,
            simple_keyword_matches=result.signals.simple_keyword_matches,
            complex_keyword_matches=result.signals.complex_keyword_matches,
            is_epic=result.signals.is_epic,
            is_subtask=result.signals.is_subtask,
            is_critical=result.signals.is_critical,
            raw_score=result.signals.raw_score,
        ),
    )
