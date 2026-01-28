"""Worker API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, WorkerRepository
from ringmaster.domain import TaskStatus, Worker, WorkerStatus
from ringmaster.worker.output_buffer import output_buffer

logger = logging.getLogger(__name__)
router = APIRouter()


class CurrentTaskInfo(BaseModel):
    """Information about a worker's current task."""

    task_id: str
    title: str
    status: str
    started_at: str | None = None
    attempts: int = 0
    max_attempts: int = 5


class WorkerWithTask(BaseModel):
    """Worker with optional current task information."""

    id: str
    name: str
    type: str
    status: WorkerStatus
    current_task_id: str | None = None
    capabilities: list[str] = []
    command: str
    args: list[str] = []
    prompt_flag: str = "-p"
    working_dir: str | None = None
    timeout_seconds: int = 1800
    env_vars: dict[str, str] = {}
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_completion_seconds: float | None = None
    created_at: str
    last_active_at: str | None = None
    # Enriched task info
    current_task: CurrentTaskInfo | None = None


class WorkerCreate(BaseModel):
    """Request body for creating a worker."""

    name: str
    type: str  # claude-code, aider, codex, etc.
    command: str
    args: list[str] = []
    prompt_flag: str = "-p"
    working_dir: str | None = None
    timeout_seconds: int = 1800
    env_vars: dict[str, str] = {}
    capabilities: list[str] = []  # e.g., ["python", "typescript", "security"]


class WorkerUpdate(BaseModel):
    """Request body for updating a worker."""

    name: str | None = None
    status: WorkerStatus | None = None
    command: str | None = None
    args: list[str] | None = None
    prompt_flag: str | None = None
    working_dir: str | None = None
    timeout_seconds: int | None = None
    env_vars: dict[str, str] | None = None
    capabilities: list[str] | None = None


class CapabilityUpdate(BaseModel):
    """Request body for adding/removing a capability."""

    capability: str


@router.get("")
async def list_workers(
    db: Annotated[Database, Depends(get_db)],
    status: WorkerStatus | None = None,
    worker_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Worker]:
    """List workers with optional filters."""
    filter_params = {
        "status": status.value if status else None,
        "worker_type": worker_type,
        "limit": limit,
        "offset": offset,
    }
    logger.info(f"Listing workers with filters: {filter_params}")

    repo = WorkerRepository(db)
    workers = await repo.list(status=status, worker_type=worker_type, limit=limit, offset=offset)

    logger.info(f"Found {len(workers)} workers")
    return workers


@router.get("/with-tasks")
async def list_workers_with_tasks(
    db: Annotated[Database, Depends(get_db)],
    status: WorkerStatus | None = None,
    worker_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[WorkerWithTask]:
    """List workers with their current task information.

    For busy workers, includes task title, started_at, and iteration info.
    This enables the UI to show duration and task context.
    """
    filter_params = {
        "status": status.value if status else None,
        "worker_type": worker_type,
        "limit": limit,
        "offset": offset,
    }
    logger.info(f"Listing workers with tasks with filters: {filter_params}")

    from ringmaster.db import TaskRepository

    repo = WorkerRepository(db)
    task_repo = TaskRepository(db)

    workers = await repo.list(status=status, worker_type=worker_type, limit=limit, offset=offset)

    result = []
    for worker in workers:
        worker_dict = worker.model_dump()
        worker_dict["created_at"] = worker.created_at.isoformat()
        worker_dict["last_active_at"] = (
            worker.last_active_at.isoformat() if worker.last_active_at else None
        )

        current_task = None
        if worker.current_task_id:
            task = await task_repo.get_task(worker.current_task_id)
            if task:
                current_task = CurrentTaskInfo(
                    task_id=task.id,
                    title=task.title,
                    status=task.status.value,
                    started_at=task.started_at.isoformat() if task.started_at else None,
                    attempts=task.attempts,
                    max_attempts=task.max_attempts,
                )

        result.append(WorkerWithTask(
            **{k: v for k, v in worker_dict.items() if k not in ("created_at", "last_active_at")},
            created_at=worker.created_at.isoformat(),
            last_active_at=worker.last_active_at.isoformat() if worker.last_active_at else None,
            current_task=current_task,
        ))

    workers_with_current_tasks = len([w for w in result if w.current_task is not None])
    logger.info(f"Found {len(result)} workers, {workers_with_current_tasks} with current tasks")
    return result


@router.post("", status_code=201)
async def create_worker(
    db: Annotated[Database, Depends(get_db)],
    body: WorkerCreate,
) -> Worker:
    """Create a new worker."""
    logger.info(f"Creating worker: name={body.name}, type={body.type}, capabilities={body.capabilities}")

    repo = WorkerRepository(db)
    worker = Worker(
        name=body.name,
        type=body.type,
        command=body.command,
        args=body.args,
        prompt_flag=body.prompt_flag,
        working_dir=body.working_dir,
        timeout_seconds=body.timeout_seconds,
        env_vars=body.env_vars,
        capabilities=body.capabilities,
    )
    created_worker = await repo.create(worker)

    logger.info(f"Worker created: id={created_worker.id}, name={created_worker.name}")
    return created_worker


@router.get("/{worker_id}")
async def get_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> Worker:
    """Get a worker by ID."""
    logger.info(f"Getting worker: worker_id={worker_id}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    logger.info(f"Worker retrieved: id={worker.id}, name={worker.name}, status={worker.status.value}")
    return worker


@router.patch("/{worker_id}")
async def update_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    body: WorkerUpdate,
) -> Worker:
    """Update a worker."""
    update_fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    logger.info(f"Updating worker: worker_id={worker_id}, fields={list(update_fields.keys())}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for update: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    if body.name is not None:
        worker.name = body.name
    if body.status is not None:
        worker.status = body.status
    if body.command is not None:
        worker.command = body.command
    if body.args is not None:
        worker.args = body.args
    if body.prompt_flag is not None:
        worker.prompt_flag = body.prompt_flag
    if body.working_dir is not None:
        worker.working_dir = body.working_dir
    if body.timeout_seconds is not None:
        worker.timeout_seconds = body.timeout_seconds
    if body.env_vars is not None:
        worker.env_vars = body.env_vars
    if body.capabilities is not None:
        worker.capabilities = body.capabilities

    updated_worker = await repo.update(worker)
    logger.info(f"Worker updated: id={updated_worker.id}, name={updated_worker.name}, status={updated_worker.status.value}")
    return updated_worker


@router.delete("/{worker_id}", status_code=204)
async def delete_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> None:
    """Delete a worker."""
    logger.info(f"Deleting worker: worker_id={worker_id}")

    repo = WorkerRepository(db)
    deleted = await repo.delete(worker_id)
    if not deleted:
        logger.warning(f"Worker not found for deletion: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    logger.info(f"Worker deleted: worker_id={worker_id}")


@router.post("/{worker_id}/activate", status_code=200)
async def activate_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> Worker:
    """Activate (mark as idle) a worker."""
    logger.info(f"Activating worker: worker_id={worker_id}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for activation: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    previous_status = worker.status
    worker.status = WorkerStatus.IDLE
    updated_worker = await repo.update(worker)

    logger.info(f"Worker activated: worker_id={worker_id}, previous_status={previous_status.value}, new_status={updated_worker.status.value}")
    return updated_worker


@router.post("/{worker_id}/deactivate", status_code=200)
async def deactivate_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> Worker:
    """Deactivate (mark as offline) a worker."""
    logger.info(f"Deactivating worker: worker_id={worker_id}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for deactivation: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    previous_status = worker.status
    current_task_id = worker.current_task_id
    worker.status = WorkerStatus.OFFLINE
    worker.current_task_id = None
    updated_worker = await repo.update(worker)

    logger.info(f"Worker deactivated: worker_id={worker_id}, previous_status={previous_status.value}, cleared_task_id={current_task_id}")
    return updated_worker


@router.get("/{worker_id}/capabilities")
async def get_capabilities(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> list[str]:
    """Get capabilities for a worker."""
    logger.info(f"Getting capabilities for worker: worker_id={worker_id}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for capabilities: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    logger.info(f"Worker capabilities retrieved: worker_id={worker_id}, capabilities={worker.capabilities}")
    return worker.capabilities


@router.post("/{worker_id}/capabilities", status_code=201)
async def add_capability(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    body: CapabilityUpdate,
) -> Worker:
    """Add a capability to a worker."""
    logger.info(f"Adding capability to worker: worker_id={worker_id}, capability={body.capability}")

    repo = WorkerRepository(db)
    success = await repo.add_capability(worker_id, body.capability)
    if not success:
        logger.warning(f"Worker not found for add capability: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    worker = await repo.get(worker_id)
    logger.info(f"Capability added: worker_id={worker_id}, capability={body.capability}, total_capabilities={len(worker.capabilities) if worker else 0}")
    return worker  # type: ignore


@router.delete("/{worker_id}/capabilities/{capability}")
async def remove_capability(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    capability: str,
) -> Worker:
    """Remove a capability from a worker."""
    logger.info(f"Removing capability from worker: worker_id={worker_id}, capability={capability}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for remove capability: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    if capability not in worker.capabilities:
        logger.warning(f"Capability not found on worker: worker_id={worker_id}, capability={capability}, current_capabilities={worker.capabilities}")
        raise HTTPException(status_code=404, detail="Capability not found")

    await repo.remove_capability(worker_id, capability)
    updated_worker = await repo.get(worker_id)
    logger.info(f"Capability removed: worker_id={worker_id}, capability={capability}, remaining_capabilities={updated_worker.capabilities if updated_worker else []}")
    return updated_worker  # type: ignore


@router.get("/capable/{capability}")
async def list_capable_workers(
    db: Annotated[Database, Depends(get_db)],
    capability: str,
    status: WorkerStatus | None = None,
) -> list[Worker]:
    """List workers that have a specific capability."""
    logger.info(f"Listing workers with capability: capability={capability}, status_filter={status.value if status else None}")

    repo = WorkerRepository(db)

    # Get workers with the capability
    capable_workers = await repo.get_capable_workers([capability])

    # Filter by status if specified
    if status:
        capable_workers = [w for w in capable_workers if w.status == status]

    logger.info(f"Found {len(capable_workers)} workers with capability: capability={capability}")
    return capable_workers


class OutputLineResponse(BaseModel):
    """Response for a single output line."""

    line: str
    line_number: int
    timestamp: str


class OutputResponse(BaseModel):
    """Response for recent output."""

    worker_id: str
    lines: list[OutputLineResponse]
    total_lines: int


@router.get("/{worker_id}/output")
async def get_worker_output(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    since_line: int = Query(default=0, ge=0),
) -> OutputResponse:
    """Get recent output for a worker.

    Args:
        worker_id: The worker ID.
        limit: Maximum number of lines to return.
        since_line: Only return lines after this line number (for polling).

    Returns:
        Recent output lines with metadata.
    """
    logger.info(f"Getting worker output: worker_id={worker_id}, limit={limit}, since_line={since_line}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for output: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    lines = await output_buffer.get_recent(worker_id, limit=limit, since_line=since_line)
    stats = output_buffer.get_buffer_stats().get(worker_id, {"total_lines": 0})

    response = OutputResponse(
        worker_id=worker_id,
        lines=[
            OutputLineResponse(
                line=line.line,
                line_number=line.line_number,
                timestamp=line.timestamp.isoformat(),
            )
            for line in lines
        ],
        total_lines=stats.get("total_lines", 0),
    )

    logger.info(f"Worker output retrieved: worker_id={worker_id}, lines_returned={len(lines)}, total_lines={response.total_lines}")
    return response


@router.get("/{worker_id}/output/stream")
async def stream_worker_output(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> StreamingResponse:
    """Stream output for a worker using Server-Sent Events (SSE).

    This endpoint provides real-time output streaming using SSE format.
    Connect with EventSource on the frontend.

    Args:
        worker_id: The worker ID.

    Returns:
        SSE stream of output lines.
    """
    import asyncio
    import json
    from uuid import uuid4

    logger.info(f"Starting SSE stream for worker: worker_id={worker_id}")

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for SSE stream: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    subscriber_id = f"sse-{uuid4().hex[:8]}"
    logger.info(f"SSE stream initialized: worker_id={worker_id}, subscriber_id={subscriber_id}")

    async def event_generator():
        """Generate SSE events."""
        queue = await output_buffer.subscribe(worker_id, subscriber_id)
        try:
            while True:
                try:
                    # Wait for new output with timeout
                    line = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps({
                        "line": line.line,
                        "line_number": line.line_number,
                        "timestamp": line.timestamp.isoformat(),
                    })
                    yield f"data: {data}\n\n"
                except TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        finally:
            await output_buffer.unsubscribe(worker_id, subscriber_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/output/stats")
async def get_output_stats() -> dict:
    """Get output buffer statistics for all workers.

    Returns:
        Dict of worker_id -> buffer stats.
    """
    logger.info("Getting output buffer statistics for all workers")

    stats = output_buffer.get_buffer_stats()
    worker_count = len(stats)
    total_lines = sum(stat.get("total_lines", 0) for stat in stats.values())

    logger.info(f"Output stats retrieved: workers_with_output={worker_count}, total_lines_across_all={total_lines}")
    return stats


class CancelResponse(BaseModel):
    """Response for cancel operation."""

    success: bool
    message: str
    task_id: str | None = None


class InterruptResponse(BaseModel):
    """Response for interrupt/pause operation."""

    success: bool
    message: str
    worker_id: str


@router.post("/{worker_id}/cancel")
async def cancel_worker_task(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> CancelResponse:
    """Cancel the current task of a busy worker.

    This immediately cancels the running task and marks both
    the worker as idle and the task as failed.

    Args:
        worker_id: The worker ID.

    Returns:
        CancelResponse with success status.
    """
    logger.info(f"Cancelling worker task: worker_id={worker_id}")

    from ringmaster.events import EventBus, EventType

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for cancellation: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.status != WorkerStatus.BUSY:
        logger.warning(f"Worker is not busy, cannot cancel: worker_id={worker_id}, status={worker.status.value}")
        raise HTTPException(
            status_code=400,
            detail=f"Worker is not busy (status: {worker.status.value})"
        )

    task_id = worker.current_task_id
    if not task_id:
        logger.warning(f"Worker has no current task to cancel: worker_id={worker_id}")
        raise HTTPException(status_code=400, detail="Worker has no current task")

    # Update task status to failed
    from ringmaster.db import TaskRepository
    task_repo = TaskRepository(db)
    task = await task_repo.get_task(task_id)
    if task:
        task.status = TaskStatus.FAILED
        task.worker_id = None
        await task_repo.update_task(task)

    # Mark worker as idle
    worker.status = WorkerStatus.IDLE
    worker.current_task_id = None
    await repo.update(worker)

    # Emit cancellation event
    event_bus = EventBus()
    await event_bus.emit(
        EventType.WORKER_TASK_CANCELLED,
        {
            "worker_id": worker_id,
            "task_id": task_id,
            "reason": "User cancelled",
        },
    )

    response = CancelResponse(
        success=True,
        message=f"Cancelled task {task_id} on worker {worker_id}",
        task_id=task_id,
    )

    logger.info(f"Worker task cancelled successfully: worker_id={worker_id}, task_id={task_id}")
    return response


@router.post("/{worker_id}/pause")
async def pause_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> InterruptResponse:
    """Pause a worker (graceful - finish current iteration).

    This marks the worker for pausing. The worker will complete
    its current task iteration and then become idle instead of
    picking up new tasks.

    Args:
        worker_id: The worker ID.

    Returns:
        InterruptResponse with success status.
    """
    logger.info(f"Pausing worker: worker_id={worker_id}")

    from ringmaster.events import EventBus, EventType

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for pause: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.status == WorkerStatus.OFFLINE:
        logger.warning(f"Worker is already offline, cannot pause: worker_id={worker_id}")
        raise HTTPException(status_code=400, detail="Worker is offline")

    # Mark worker as paused (using OFFLINE status since we don't have PAUSED)
    # The worker will finish its current task and not pick up new ones
    previous_status = worker.status
    worker.status = WorkerStatus.OFFLINE

    # Don't clear current_task_id - let task complete
    await repo.update(worker)

    # Emit pause event
    event_bus = EventBus()
    await event_bus.emit(
        EventType.WORKER_PAUSED,
        {
            "worker_id": worker_id,
            "previous_status": previous_status.value,
            "current_task_id": worker.current_task_id,
        },
    )

    response = InterruptResponse(
        success=True,
        message=f"Worker {worker_id} paused. Current task will complete.",
        worker_id=worker_id,
    )

    logger.info(f"Worker paused successfully: worker_id={worker_id}, previous_status={previous_status.value}, current_task_id={worker.current_task_id}")
    return response


class PauseAllResponse(BaseModel):
    """Response for pausing all workers."""

    success: bool
    message: str
    paused_count: int
    paused_worker_ids: list[str]
    skipped_count: int


@router.post("/pause-all")
async def pause_all_workers(
    db: Annotated[Database, Depends(get_db)],
) -> PauseAllResponse:
    """Pause all active workers (graceful - finish current iterations).

    This marks all non-offline workers for pausing. Each worker will complete
    its current task iteration and then become offline instead of picking up
    new tasks.

    Returns:
        PauseAllResponse with count of paused workers.
    """
    logger.info("Pausing all active workers")

    from ringmaster.events import EventBus, EventType

    repo = WorkerRepository(db)

    # Get all non-offline workers
    all_workers = await repo.list(limit=1000)
    active_workers = [w for w in all_workers if w.status != WorkerStatus.OFFLINE]

    logger.info(f"Found {len(active_workers)} active workers to pause out of {len(all_workers)} total workers")

    if not active_workers:
        return PauseAllResponse(
            success=True,
            message="No active workers to pause.",
            paused_count=0,
            paused_worker_ids=[],
            skipped_count=0,
        )

    paused_ids = []
    event_bus = EventBus()

    for worker in active_workers:
        previous_status = worker.status
        worker.status = WorkerStatus.OFFLINE
        # Don't clear current_task_id - let task complete
        await repo.update(worker)
        paused_ids.append(worker.id)

        # Emit pause event for each worker
        await event_bus.emit(
            EventType.WORKER_PAUSED,
            {
                "worker_id": worker.id,
                "previous_status": previous_status.value,
                "current_task_id": worker.current_task_id,
            },
        )

    response = PauseAllResponse(
        success=True,
        message=f"Paused {len(paused_ids)} worker(s). Current tasks will complete.",
        paused_count=len(paused_ids),
        paused_worker_ids=paused_ids,
        skipped_count=0,
    )

    logger.info(f"All active workers paused successfully: paused_count={len(paused_ids)}, worker_ids={paused_ids}")
    return response


# =============================================================================
# Tmux Worker Spawning Endpoints
# =============================================================================


class SpawnWorkerRequest(BaseModel):
    """Request body for spawning a worker in tmux."""

    worker_type: str = "claude-code"  # claude-code, aider, codex, goose, generic
    capabilities: list[str] = []
    worktree_path: str | None = None
    custom_command: str | None = None


class SpawnedWorkerResponse(BaseModel):
    """Response for a spawned worker."""

    worker_id: str
    worker_type: str
    tmux_session: str
    log_path: str | None
    status: str
    attach_command: str


class TmuxSessionResponse(BaseModel):
    """Response for a tmux session."""

    session_name: str
    worker_id: str
    attach_command: str


@router.post("/{worker_id}/spawn", status_code=201)
async def spawn_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    body: SpawnWorkerRequest,
) -> SpawnedWorkerResponse:
    """Spawn a worker in a new tmux session.

    Creates a new tmux session running a worker script that:
    - Polls for tasks via `ringmaster pull-bead`
    - Builds prompts via `ringmaster build-prompt`
    - Executes the worker CLI (claude, aider, etc.)
    - Reports results via `ringmaster report-result`

    Args:
        worker_id: Unique worker identifier.
        body: Spawn configuration.

    Returns:
        SpawnedWorkerResponse with session details.
    """
    logger.info(f"Spawning worker: worker_id={worker_id}, type={body.worker_type}, capabilities={body.capabilities}")

    from ringmaster.events import EventBus, EventType
    from ringmaster.worker.spawner import WorkerSpawner

    repo = WorkerRepository(db)

    # Check if worker exists, create if not
    worker = await repo.get(worker_id)
    if not worker:
        worker = Worker(
            id=worker_id,
            name=worker_id,
            type=body.worker_type,
            command=body.custom_command or body.worker_type,
            capabilities=body.capabilities,
        )
        await repo.create(worker)
    else:
        # Update capabilities if provided
        if body.capabilities:
            worker.capabilities = body.capabilities
            await repo.update(worker)

    # Create spawner and spawn
    spawner = WorkerSpawner(db_path=db.db_path)

    try:
        spawned = await spawner.spawn(
            worker_id=worker_id,
            worker_type=body.worker_type,
            capabilities=body.capabilities,
            worktree_path=body.worktree_path,
            custom_command=body.custom_command,
        )

        # Update worker status to idle (ready to work)
        worker.status = WorkerStatus.IDLE
        await repo.update(worker)

        # Emit spawn event
        event_bus = EventBus()
        await event_bus.emit(
            EventType.WORKER_UPDATED,
            {
                "worker_id": worker_id,
                "action": "spawned",
                "tmux_session": spawned.tmux_session,
            },
        )

        response = SpawnedWorkerResponse(
            worker_id=spawned.worker_id,
            worker_type=spawned.worker_type,
            tmux_session=spawned.tmux_session,
            log_path=spawned.log_path,
            status=spawned.status.value,
            attach_command=spawner.attach_command(worker_id),
        )

        logger.info(f"Worker spawned successfully: worker_id={worker_id}, tmux_session={spawned.tmux_session}, log_path={spawned.log_path}")
        return response

    except RuntimeError as e:
        logger.warning(f"Failed to spawn worker: worker_id={worker_id}, error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{worker_id}/kill")
async def kill_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> InterruptResponse:
    """Kill a worker's tmux session.

    This terminates the tmux session and marks the worker as offline.
    Any running task will be interrupted.

    Args:
        worker_id: The worker ID.

    Returns:
        InterruptResponse with success status.
    """
    logger.info(f"Killing worker: worker_id={worker_id}")

    from ringmaster.events import EventBus, EventType
    from ringmaster.worker.spawner import WorkerSpawner

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for kill: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    # Kill the tmux session
    spawner = WorkerSpawner()
    success = await spawner.kill(worker_id)

    if not success:
        # Session may not exist, still update DB
        logger.info(f"Tmux session may not have existed for worker: worker_id={worker_id}")

    # Update worker status
    worker.status = WorkerStatus.OFFLINE
    worker.current_task_id = None
    await repo.update(worker)

    # Emit kill event
    event_bus = EventBus()
    await event_bus.emit(
        EventType.WORKER_UPDATED,
        {
            "worker_id": worker_id,
            "action": "killed",
        },
    )

    response = InterruptResponse(
        success=True,
        message=f"Worker {worker_id} killed",
        worker_id=worker_id,
    )

    logger.info(f"Worker killed successfully: worker_id={worker_id}, tmux_session_killed={success}")
    return response


@router.get("/{worker_id}/session")
async def get_worker_session(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> TmuxSessionResponse:
    """Get tmux session info for a worker.

    Args:
        worker_id: The worker ID.

    Returns:
        TmuxSessionResponse with session details.
    """
    logger.info(f"Getting worker session info: worker_id={worker_id}")

    from ringmaster.worker.spawner import WorkerSpawner

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for session info: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    spawner = WorkerSpawner()
    session_name = spawner._get_tmux_session_name(worker_id)

    # Check if session is running
    if not await spawner.is_running(worker_id):
        logger.warning(f"Worker session not running: worker_id={worker_id}, session_name={session_name}")
        raise HTTPException(status_code=404, detail="Worker session not running")

    response = TmuxSessionResponse(
        session_name=session_name,
        worker_id=worker_id,
        attach_command=spawner.attach_command(worker_id),
    )

    logger.info(f"Worker session info retrieved: worker_id={worker_id}, session_name={session_name}")
    return response


@router.get("/sessions/list")
async def list_worker_sessions() -> list[TmuxSessionResponse]:
    """List all running worker tmux sessions.

    Returns:
        List of running worker sessions.
    """
    logger.info("Listing all worker tmux sessions")

    from ringmaster.worker.spawner import WorkerSpawner

    spawner = WorkerSpawner()
    sessions = await spawner.list_sessions()

    response = [
        TmuxSessionResponse(
            session_name=session,
            worker_id=session.replace("rm-worker-", ""),
            attach_command=f"tmux attach -t {session}",
        )
        for session in sessions
    ]

    logger.info(f"Found {len(response)} running worker sessions: {[s.session_name for s in response]}")
    return response


class WorkerLogResponse(BaseModel):
    """Response for worker log output."""

    worker_id: str
    log_path: str | None
    output: str | None
    lines_count: int


# =============================================================================
# Worker Health Monitoring Endpoints
# =============================================================================


class DegradationSignalsResponse(BaseModel):
    """Signals indicating potential context degradation."""

    repetition_score: float = 0.0
    apology_count: int = 0
    retry_count: int = 0
    contradiction_count: int = 0
    is_degraded: bool = False


class RecoveryActionResponse(BaseModel):
    """Recommended recovery action."""

    action: str  # "none", "log_warning", "interrupt", "checkpoint_restart", "escalate"
    reason: str
    urgency: str  # "low", "medium", "high", "critical"


class WorkerHealthResponse(BaseModel):
    """Worker health status and monitoring information."""

    worker_id: str
    task_id: str | None = None
    liveness_status: str  # "active", "thinking", "slow", "likely_hung", "degraded"
    degradation: DegradationSignalsResponse
    recommended_action: RecoveryActionResponse
    runtime_seconds: float
    idle_seconds: float
    total_output_lines: int


@router.get("/{worker_id}/health")
async def get_worker_health(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> WorkerHealthResponse:
    """Get health status for a worker based on output monitoring.

    Analyzes worker output for:
    - Liveness: Is the worker still producing output?
    - Degradation: Is the worker showing signs of context drift?
    - Recovery: What action should be taken?

    This endpoint requires the worker to be actively monitored via
    the output buffer. Workers that haven't produced output will
    show as "unknown" state.

    Args:
        worker_id: The worker ID.

    Returns:
        WorkerHealthResponse with health analysis.
    """
    logger.info(f"Getting worker health: worker_id={worker_id}")

    from ringmaster.worker.monitor import (
        LivenessStatus,
        WorkerMonitor,
        recommend_recovery,
    )

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for health check: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    # Get recent output from buffer for analysis
    lines = await output_buffer.get_recent(worker_id, limit=500)

    # Create monitor and feed output
    monitor = WorkerMonitor(
        worker_id=worker_id,
        task_id=worker.current_task_id,
    )

    for line in lines:
        await monitor.record_output(line.line)

    # Check health
    liveness = monitor.check_liveness()
    degradation = monitor.check_degradation()
    recovery = recommend_recovery(monitor)

    # Map liveness status to string
    liveness_map = {
        LivenessStatus.ACTIVE: "active",
        LivenessStatus.THINKING: "thinking",
        LivenessStatus.SLOW: "slow",
        LivenessStatus.LIKELY_HUNG: "likely_hung",
        LivenessStatus.DEGRADED: "degraded",
    }

    response = WorkerHealthResponse(
        worker_id=worker_id,
        task_id=worker.current_task_id,
        liveness_status=liveness_map.get(liveness, "unknown"),
        degradation=DegradationSignalsResponse(
            repetition_score=degradation.repetition_score,
            apology_count=degradation.apology_count,
            retry_count=degradation.retry_count,
            contradiction_count=degradation.contradiction_count,
            is_degraded=degradation.is_degraded,
        ),
        recommended_action=RecoveryActionResponse(
            action=recovery.action,
            reason=recovery.reason,
            urgency=recovery.urgency,
        ),
        runtime_seconds=monitor.get_runtime().total_seconds(),
        idle_seconds=monitor.get_idle_time().total_seconds(),
        total_output_lines=len(monitor.state.output_lines),
    )

    logger.info(f"Worker health retrieved: worker_id={worker_id}, liveness_status={response.liveness_status}, is_degraded={response.degradation.is_degraded}, recommended_action={response.recommended_action.action}")
    return response


@router.get("/{worker_id}/log")
async def get_worker_log(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    lines: int = Query(default=100, ge=1, le=10000),
) -> WorkerLogResponse:
    """Get recent log output from a worker's log file.

    This reads from the worker's log file (not the output buffer).
    Use this for workers running in tmux sessions.

    Args:
        worker_id: The worker ID.
        lines: Number of lines to retrieve.

    Returns:
        WorkerLogResponse with log output.
    """
    logger.info(f"Getting worker log: worker_id={worker_id}, lines={lines}")

    from ringmaster.worker.spawner import WorkerSpawner

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        logger.warning(f"Worker not found for log: worker_id={worker_id}")
        raise HTTPException(status_code=404, detail="Worker not found")

    spawner = WorkerSpawner()
    output = await spawner.get_output(worker_id, lines)
    log_path = spawner.log_dir / f"{worker_id}.log"

    response = WorkerLogResponse(
        worker_id=worker_id,
        log_path=str(log_path) if log_path.exists() else None,
        output=output,
        lines_count=len(output.split("\n")) if output else 0,
    )

    logger.info(f"Worker log retrieved: worker_id={worker_id}, log_path_exists={log_path.exists() if log_path else False}, lines_count={response.lines_count}")
    return response


# =============================================================================
# Worktree Management Endpoints
# =============================================================================


class WorktreeInfo(BaseModel):
    """Information about a git worktree."""

    path: str
    branch: str
    commit_hash: str
    is_detached: bool = False
    is_locked: bool = False
    is_prunable: bool = False


class WorktreeListResponse(BaseModel):
    """Response for listing worktrees."""

    repo_path: str
    worktrees: list[WorktreeInfo]
    prunable_count: int


class WorktreePruneResponse(BaseModel):
    """Response for pruning worktrees."""

    repo_path: str
    pruned_count: int
    remaining_count: int


@router.post("/worktrees/list")
async def list_worktrees_api(
    repo_path: str = Query(..., description="Path to the git repository"),
) -> WorktreeListResponse:
    """List all worktrees for a repository.

    Args:
        repo_path: Path to the main git repository.

    Returns:
        WorktreeListResponse with worktree information.
    """
    logger.info(f"Listing worktrees: repo_path={repo_path}")

    from pathlib import Path

    from ringmaster.git.worktrees import list_worktrees

    repo = Path(repo_path).resolve()
    if not repo.exists():
        logger.warning(f"Repository not found: repo_path={repo_path}")
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_path}")

    worktrees = await list_worktrees(repo)

    response = WorktreeListResponse(
        repo_path=str(repo),
        worktrees=[
            WorktreeInfo(
                path=str(wt.path),
                branch=wt.branch,
                commit_hash=wt.commit_hash,
                is_detached=wt.is_detached,
                is_locked=wt.is_locked,
                is_prunable=wt.is_prunable,
            )
            for wt in worktrees
        ],
        prunable_count=sum(1 for wt in worktrees if wt.is_prunable),
    )

    logger.info(f"Worktrees listed: repo_path={repo_path}, total_worktrees={len(response.worktrees)}, prunable_count={response.prunable_count}")
    return response


@router.post("/worktrees/prune")
async def prune_worktrees_api(
    repo_path: str = Query(..., description="Path to the git repository"),
) -> WorktreePruneResponse:
    """Prune stale worktrees for a repository.

    Removes worktrees whose directories no longer exist. This can happen
    when worker directories are deleted without using 'git worktree remove'.

    Args:
        repo_path: Path to the main git repository.

    Returns:
        WorktreePruneResponse with prune results.
    """
    logger.info(f"Pruning worktrees: repo_path={repo_path}")

    from pathlib import Path

    from ringmaster.git.worktrees import clean_stale_worktrees, list_worktrees

    repo = Path(repo_path).resolve()
    if not repo.exists():
        logger.warning(f"Repository not found for pruning: repo_path={repo_path}")
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_path}")

    # Prune
    removed = await clean_stale_worktrees(repo)

    # Count after pruning
    worktrees_after = await list_worktrees(repo)

    response = WorktreePruneResponse(
        repo_path=str(repo),
        pruned_count=removed,
        remaining_count=len(worktrees_after),
    )

    logger.info(f"Worktrees pruned: repo_path={repo_path}, pruned_count={removed}, remaining_count={response.remaining_count}")
    return response
