"""Worker API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, WorkerRepository
from ringmaster.domain import Worker, WorkerStatus

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
