"""Worker API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, WorkerRepository
from ringmaster.domain import TaskStatus, Worker, WorkerStatus
from ringmaster.worker.output_buffer import output_buffer

router = APIRouter()


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
    repo = WorkerRepository(db)
    return await repo.list(status=status, worker_type=worker_type, limit=limit, offset=offset)


@router.post("", status_code=201)
async def create_worker(
    db: Annotated[Database, Depends(get_db)],
    body: WorkerCreate,
) -> Worker:
    """Create a new worker."""
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
    return await repo.create(worker)


@router.get("/{worker_id}")
async def get_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> Worker:
    """Get a worker by ID."""
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


@router.patch("/{worker_id}")
async def update_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    body: WorkerUpdate,
) -> Worker:
    """Update a worker."""
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
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

    return await repo.update(worker)


@router.delete("/{worker_id}", status_code=204)
async def delete_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> None:
    """Delete a worker."""
    repo = WorkerRepository(db)
    deleted = await repo.delete(worker_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Worker not found")


@router.post("/{worker_id}/activate", status_code=200)
async def activate_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> Worker:
    """Activate (mark as idle) a worker."""
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    worker.status = WorkerStatus.IDLE
    return await repo.update(worker)


@router.post("/{worker_id}/deactivate", status_code=200)
async def deactivate_worker(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> Worker:
    """Deactivate (mark as offline) a worker."""
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    worker.status = WorkerStatus.OFFLINE
    worker.current_task_id = None
    return await repo.update(worker)


@router.get("/{worker_id}/capabilities")
async def get_capabilities(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
) -> list[str]:
    """Get capabilities for a worker."""
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker.capabilities


@router.post("/{worker_id}/capabilities", status_code=201)
async def add_capability(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    body: CapabilityUpdate,
) -> Worker:
    """Add a capability to a worker."""
    repo = WorkerRepository(db)
    success = await repo.add_capability(worker_id, body.capability)
    if not success:
        raise HTTPException(status_code=404, detail="Worker not found")

    worker = await repo.get(worker_id)
    return worker  # type: ignore


@router.delete("/{worker_id}/capabilities/{capability}")
async def remove_capability(
    db: Annotated[Database, Depends(get_db)],
    worker_id: str,
    capability: str,
) -> Worker:
    """Remove a capability from a worker."""
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if capability not in worker.capabilities:
        raise HTTPException(status_code=404, detail="Capability not found")

    await repo.remove_capability(worker_id, capability)
    return await repo.get(worker_id)  # type: ignore


@router.get("/capable/{capability}")
async def list_capable_workers(
    db: Annotated[Database, Depends(get_db)],
    capability: str,
    status: WorkerStatus | None = None,
) -> list[Worker]:
    """List workers that have a specific capability."""
    repo = WorkerRepository(db)

    # Get workers with the capability
    capable_workers = await repo.get_capable_workers([capability])

    # Filter by status if specified
    if status:
        capable_workers = [w for w in capable_workers if w.status == status]

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
    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    lines = await output_buffer.get_recent(worker_id, limit=limit, since_line=since_line)
    stats = output_buffer.get_buffer_stats().get(worker_id, {"total_lines": 0})

    return OutputResponse(
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

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    subscriber_id = f"sse-{uuid4().hex[:8]}"

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
    return output_buffer.get_buffer_stats()


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
    from ringmaster.events import EventBus, EventType

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.status != WorkerStatus.BUSY:
        raise HTTPException(
            status_code=400,
            detail=f"Worker is not busy (status: {worker.status.value})"
        )

    task_id = worker.current_task_id
    if not task_id:
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

    return CancelResponse(
        success=True,
        message=f"Cancelled task {task_id} on worker {worker_id}",
        task_id=task_id,
    )


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
    from ringmaster.events import EventBus, EventType

    repo = WorkerRepository(db)
    worker = await repo.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.status == WorkerStatus.OFFLINE:
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

    return InterruptResponse(
        success=True,
        message=f"Worker {worker_id} paused. Current task will complete.",
        worker_id=worker_id,
    )
