"""Undo/Redo API routes for action reversibility.

Implements the Reversibility UX pattern from docs/07-user-experience.md:
- GET /api/undo/history - List recent actions
- GET /api/undo/last - Get last undoable action
- POST /api/undo - Undo the last action
- POST /api/redo - Redo the last undone action
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database
from ringmaster.db.repositories import ActionRepository, TaskRepository, WorkerRepository
from ringmaster.domain import Action, ActionType, EntityType
from ringmaster.events import event_bus
from ringmaster.events.types import EventType

router = APIRouter(prefix="/api/undo", tags=["undo"])


class ActionResponse(BaseModel):
    """Response model for an action."""

    id: int
    action_type: str
    entity_type: str
    entity_id: str
    description: str
    project_id: str | None
    undone: bool
    created_at: str
    actor_type: str
    actor_id: str | None


class UndoResponse(BaseModel):
    """Response for undo/redo operations."""

    success: bool
    action: ActionResponse | None
    message: str


class HistoryResponse(BaseModel):
    """Response for action history list."""

    actions: list[ActionResponse]
    can_undo: bool
    can_redo: bool


def _action_to_response(action: Action) -> ActionResponse:
    """Convert an Action domain model to response format."""
    return ActionResponse(
        id=action.id or 0,
        action_type=action.action_type.value,
        entity_type=action.entity_type.value,
        entity_id=action.entity_id,
        description=action.description(),
        project_id=str(action.project_id) if action.project_id else None,
        undone=action.undone,
        created_at=action.created_at.isoformat(),
        actor_type=action.actor_type.value,
        actor_id=action.actor_id,
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    include_undone: bool = Query(False),
):
    """Get recent action history.

    Returns a list of recent actions that can be undone,
    along with flags indicating if undo/redo are available.
    """
    action_repo = ActionRepository(db)

    actions = await action_repo.get_recent(
        project_id=project_id,
        limit=limit,
        include_undone=include_undone,
    )

    last_undoable = await action_repo.get_last_undoable(project_id)
    last_redoable = await action_repo.get_last_redoable(project_id)

    return HistoryResponse(
        actions=[_action_to_response(a) for a in actions],
        can_undo=last_undoable is not None,
        can_redo=last_redoable is not None,
    )


@router.get("/last", response_model=ActionResponse | None)
async def get_last_undoable(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = Query(None),
):
    """Get the last action that can be undone."""
    action_repo = ActionRepository(db)

    action = await action_repo.get_last_undoable(project_id)
    if not action:
        return None

    return _action_to_response(action)


@router.post("", response_model=UndoResponse)
async def undo(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = Query(None),
):
    """Undo the last action.

    Restores the previous state of the affected entity.
    """
    action_repo = ActionRepository(db)
    task_repo = TaskRepository(db)
    worker_repo = WorkerRepository(db)

    # Get last undoable action
    action = await action_repo.get_last_undoable(project_id)
    if not action:
        return UndoResponse(
            success=False,
            action=None,
            message="Nothing to undo",
        )

    # Perform the undo based on action type
    try:
        await _apply_undo(action, task_repo, worker_repo)

        # Mark action as undone
        await action_repo.mark_undone(action.id)  # type: ignore

        # Emit event
        await event_bus.emit(
            EventType.UNDO_PERFORMED,
            {
                "action_id": action.id,
                "action_type": action.action_type.value,
                "entity_type": action.entity_type.value,
                "entity_id": action.entity_id,
            },
            project_id=str(action.project_id) if action.project_id else None,
        )

        return UndoResponse(
            success=True,
            action=_action_to_response(action),
            message=f"Undone: {action.description()}",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Undo failed: {e!s}") from e


@router.post("/redo", response_model=UndoResponse)
async def redo(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = Query(None),
):
    """Redo the last undone action.

    Re-applies the new state of the affected entity.
    """
    action_repo = ActionRepository(db)
    task_repo = TaskRepository(db)
    worker_repo = WorkerRepository(db)

    # Get last redoable action
    action = await action_repo.get_last_redoable(project_id)
    if not action:
        return UndoResponse(
            success=False,
            action=None,
            message="Nothing to redo",
        )

    # Perform the redo
    try:
        await _apply_redo(action, task_repo, worker_repo)

        # Mark action as redone
        await action_repo.mark_redone(action.id)  # type: ignore

        # Emit event
        await event_bus.emit(
            EventType.REDO_PERFORMED,
            {
                "action_id": action.id,
                "action_type": action.action_type.value,
                "entity_type": action.entity_type.value,
                "entity_id": action.entity_id,
            },
            project_id=str(action.project_id) if action.project_id else None,
        )

        return UndoResponse(
            success=True,
            action=_action_to_response(action),
            message=f"Redone: {action.description()}",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redo failed: {e!s}") from e


async def _apply_undo(
    action: Action,
    task_repo: TaskRepository,
    worker_repo: WorkerRepository,
) -> None:
    """Apply the undo operation by restoring previous state."""

    if action.entity_type == EntityType.TASK:
        await _undo_task_action(action, task_repo)
    elif action.entity_type == EntityType.WORKER:
        await _undo_worker_action(action, worker_repo)
    elif action.entity_type == EntityType.DEPENDENCY:
        await _undo_dependency_action(action, task_repo)
    else:
        raise ValueError(f"Unsupported entity type for undo: {action.entity_type}")


async def _apply_redo(
    action: Action,
    task_repo: TaskRepository,
    worker_repo: WorkerRepository,
) -> None:
    """Apply the redo operation by restoring new state."""

    if action.entity_type == EntityType.TASK:
        await _redo_task_action(action, task_repo)
    elif action.entity_type == EntityType.WORKER:
        await _redo_worker_action(action, worker_repo)
    elif action.entity_type == EntityType.DEPENDENCY:
        await _redo_dependency_action(action, task_repo)
    else:
        raise ValueError(f"Unsupported entity type for redo: {action.entity_type}")


async def _undo_task_action(action: Action, task_repo: TaskRepository) -> None:
    """Undo a task-related action."""
    from ringmaster.domain import Priority, TaskStatus

    if action.action_type == ActionType.TASK_CREATED:
        # Undo create = delete
        await task_repo.delete_task(action.entity_id)

    elif action.action_type == ActionType.TASK_DELETED:
        # Undo delete = recreate from previous_state
        if not action.previous_state:
            raise ValueError("Cannot undo delete: no previous state")

        task = _dict_to_task(action.previous_state)
        await task_repo.create_task(task)

    elif action.action_type in (ActionType.TASK_UPDATED, ActionType.TASK_STATUS_CHANGED):
        # Undo update = restore previous state
        if not action.previous_state:
            raise ValueError("Cannot undo update: no previous state")

        task = await task_repo.get_task(action.entity_id)
        if not task:
            raise ValueError(f"Task {action.entity_id} not found")

        # Restore fields from previous state
        task.title = action.previous_state.get("title", task.title)
        task.description = action.previous_state.get("description", task.description)
        task.priority = Priority(action.previous_state.get("priority", task.priority.value))
        task.status = TaskStatus(action.previous_state.get("status", task.status.value))

        if hasattr(task, "worker_id"):
            task.worker_id = action.previous_state.get("worker_id")

        await task_repo.update_task(task)


async def _redo_task_action(action: Action, task_repo: TaskRepository) -> None:
    """Redo a task-related action."""
    from ringmaster.domain import Priority, TaskStatus

    if action.action_type == ActionType.TASK_CREATED:
        # Redo create = recreate from new_state
        if not action.new_state:
            raise ValueError("Cannot redo create: no new state")

        task = _dict_to_task(action.new_state)
        await task_repo.create_task(task)

    elif action.action_type == ActionType.TASK_DELETED:
        # Redo delete = delete again
        await task_repo.delete_task(action.entity_id)

    elif action.action_type in (ActionType.TASK_UPDATED, ActionType.TASK_STATUS_CHANGED):
        # Redo update = apply new state
        if not action.new_state:
            raise ValueError("Cannot redo update: no new state")

        task = await task_repo.get_task(action.entity_id)
        if not task:
            raise ValueError(f"Task {action.entity_id} not found")

        # Apply new state
        task.title = action.new_state.get("title", task.title)
        task.description = action.new_state.get("description", task.description)
        task.priority = Priority(action.new_state.get("priority", task.priority.value))
        task.status = TaskStatus(action.new_state.get("status", task.status.value))

        if hasattr(task, "worker_id"):
            task.worker_id = action.new_state.get("worker_id")

        await task_repo.update_task(task)


async def _undo_worker_action(action: Action, worker_repo: WorkerRepository) -> None:
    """Undo a worker-related action."""
    from ringmaster.domain import WorkerStatus

    if action.action_type in (ActionType.WORKER_ASSIGNED, ActionType.WORKER_UNASSIGNED):
        # Restore worker's previous state
        if not action.previous_state:
            raise ValueError("Cannot undo worker action: no previous state")

        worker = await worker_repo.get(action.entity_id)
        if not worker:
            raise ValueError(f"Worker {action.entity_id} not found")

        worker.current_task_id = action.previous_state.get("current_task_id")
        worker.status = WorkerStatus(action.previous_state.get("status", worker.status.value))

        await worker_repo.update(worker)


async def _redo_worker_action(action: Action, worker_repo: WorkerRepository) -> None:
    """Redo a worker-related action."""
    from ringmaster.domain import WorkerStatus

    if action.action_type in (ActionType.WORKER_ASSIGNED, ActionType.WORKER_UNASSIGNED):
        # Apply new state
        if not action.new_state:
            raise ValueError("Cannot redo worker action: no new state")

        worker = await worker_repo.get(action.entity_id)
        if not worker:
            raise ValueError(f"Worker {action.entity_id} not found")

        worker.current_task_id = action.new_state.get("current_task_id")
        worker.status = WorkerStatus(action.new_state.get("status", worker.status.value))

        await worker_repo.update(worker)


async def _undo_dependency_action(action: Action, task_repo: TaskRepository) -> None:
    """Undo a dependency-related action."""
    from ringmaster.domain import Dependency

    if action.action_type == ActionType.DEPENDENCY_CREATED:
        # Undo create = delete
        if action.previous_state:
            child_id = action.previous_state.get("child_id", "")
            parent_id = action.previous_state.get("parent_id", "")
        else:
            # Parse from entity_id if needed (format: "child_id:parent_id")
            parts = action.entity_id.split(":")
            if len(parts) == 2:
                child_id, parent_id = parts
            else:
                raise ValueError("Cannot determine dependency IDs")

        await task_repo.remove_dependency(child_id, parent_id)

    elif action.action_type == ActionType.DEPENDENCY_DELETED:
        # Undo delete = recreate
        if not action.previous_state:
            raise ValueError("Cannot undo dependency delete: no previous state")

        dependency = Dependency(
            child_id=action.previous_state["child_id"],
            parent_id=action.previous_state["parent_id"],
        )
        await task_repo.add_dependency(dependency)


async def _redo_dependency_action(action: Action, task_repo: TaskRepository) -> None:
    """Redo a dependency-related action."""
    from ringmaster.domain import Dependency

    if action.action_type == ActionType.DEPENDENCY_CREATED:
        # Redo create = create again
        if not action.new_state:
            raise ValueError("Cannot redo dependency create: no new state")

        dependency = Dependency(
            child_id=action.new_state["child_id"],
            parent_id=action.new_state["parent_id"],
        )
        await task_repo.add_dependency(dependency)

    elif action.action_type == ActionType.DEPENDENCY_DELETED:
        # Redo delete = delete again
        if action.previous_state:
            child_id = action.previous_state.get("child_id", "")
            parent_id = action.previous_state.get("parent_id", "")
        else:
            parts = action.entity_id.split(":")
            if len(parts) == 2:
                child_id, parent_id = parts
            else:
                raise ValueError("Cannot determine dependency IDs")

        await task_repo.remove_dependency(child_id, parent_id)


def _dict_to_task(data: dict[str, Any]) -> Any:
    """Convert a dictionary back to a task model."""
    from ringmaster.domain import Epic, Priority, Subtask, Task, TaskStatus, TaskType

    task_type = TaskType(data.get("type", "task"))
    project_id = UUID(data["project_id"])
    priority = Priority(data.get("priority", "P2"))
    status = TaskStatus(data.get("status", "draft"))

    base_kwargs = {
        "id": data["id"],
        "project_id": project_id,
        "title": data["title"],
        "description": data.get("description"),
        "priority": priority,
        "status": status,
        "prompt_path": data.get("prompt_path"),
        "output_path": data.get("output_path"),
        "context_hash": data.get("context_hash"),
    }

    if task_type == TaskType.EPIC:
        return Epic(
            **base_kwargs,
            acceptance_criteria=data.get("acceptance_criteria", []),
            context=data.get("context"),
        )
    elif task_type == TaskType.SUBTASK:
        return Subtask(
            **base_kwargs,
            parent_id=data["parent_id"],
            worker_id=data.get("worker_id"),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 3),
        )
    else:
        return Task(
            **base_kwargs,
            parent_id=data.get("parent_id"),
            worker_id=data.get("worker_id"),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 5),
            pagerank_score=data.get("pagerank_score", 0),
            betweenness_score=data.get("betweenness_score", 0),
            on_critical_path=data.get("on_critical_path", False),
            combined_priority=data.get("combined_priority", 0),
        )
