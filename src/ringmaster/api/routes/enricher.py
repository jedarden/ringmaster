"""Enricher API routes for context assembly observability.

Per docs/04-context-enrichment.md "Observability" section:
Track what context is being assembled for each task to enable
debugging, analysis, and improvement of the enrichment pipeline.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database
from ringmaster.db.repositories import ContextAssemblyLogRepository

router = APIRouter()


class ContextAssemblyLogResponse(BaseModel):
    """Response model for a context assembly log entry."""

    id: int
    task_id: str
    project_id: str
    sources_queried: list[str]
    candidates_found: int
    items_included: int
    tokens_used: int
    tokens_budget: int
    compression_applied: list[str]
    compression_ratio: float
    stages_applied: list[str]
    assembly_time_ms: int
    context_hash: str | None
    created_at: str


class ContextAssemblyStatsResponse(BaseModel):
    """Response model for context assembly statistics."""

    total_assemblies: int
    avg_tokens_used: float
    avg_tokens_budget: float
    avg_assembly_time_ms: float
    avg_items_included: float
    avg_compression_ratio: float
    max_tokens_used: int
    min_tokens_used: int


@router.get("/for-task/{task_id}")
async def get_context_logs_for_task(
    task_id: str,
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ContextAssemblyLogResponse]:
    """Get context assembly logs for a specific task.

    Returns all assembly events for a task, ordered by most recent first.
    Useful for debugging why a task received certain context.
    """
    repo = ContextAssemblyLogRepository(db)
    logs = await repo.list_for_task(task_id, limit=limit)

    return [
        ContextAssemblyLogResponse(
            id=log.id,
            task_id=log.task_id,
            project_id=str(log.project_id),
            sources_queried=log.sources_queried,
            candidates_found=log.candidates_found,
            items_included=log.items_included,
            tokens_used=log.tokens_used,
            tokens_budget=log.tokens_budget,
            compression_applied=log.compression_applied,
            compression_ratio=log.compression_ratio,
            stages_applied=log.stages_applied,
            assembly_time_ms=log.assembly_time_ms,
            context_hash=log.context_hash,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/for-project/{project_id}")
async def get_context_logs_for_project(
    project_id: UUID,
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ContextAssemblyLogResponse]:
    """Get context assembly logs for a specific project.

    Returns all assembly events for a project, ordered by most recent first.
    Useful for analyzing context patterns across tasks.
    """
    repo = ContextAssemblyLogRepository(db)
    logs = await repo.list_for_project(project_id, limit=limit, offset=offset)

    return [
        ContextAssemblyLogResponse(
            id=log.id,
            task_id=log.task_id,
            project_id=str(log.project_id),
            sources_queried=log.sources_queried,
            candidates_found=log.candidates_found,
            items_included=log.items_included,
            tokens_used=log.tokens_used,
            tokens_budget=log.tokens_budget,
            compression_applied=log.compression_applied,
            compression_ratio=log.compression_ratio,
            stages_applied=log.stages_applied,
            assembly_time_ms=log.assembly_time_ms,
            context_hash=log.context_hash,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/stats/{project_id}")
async def get_context_stats(
    project_id: UUID,
    db: Annotated[Database, Depends(get_db)],
) -> ContextAssemblyStatsResponse:
    """Get aggregated context assembly statistics for a project.

    Returns average token usage, assembly times, compression ratios, etc.
    Useful for monitoring context efficiency.
    """
    repo = ContextAssemblyLogRepository(db)
    stats = await repo.get_stats(project_id)

    return ContextAssemblyStatsResponse(**stats)


@router.get("/budget-alerts/{project_id}")
async def get_budget_alerts(
    project_id: UUID,
    db: Annotated[Database, Depends(get_db)],
    threshold: float = Query(default=0.95, ge=0.5, le=1.0),
) -> list[ContextAssemblyLogResponse]:
    """Get context assembly logs where token usage exceeded threshold of budget.

    Per docs/04-context-enrichment.md:
    Alert if consistently hitting budget limits so we can tune the pipeline.

    Args:
        threshold: Minimum ratio of tokens_used/tokens_budget to alert on.
                  Default 0.95 means assemblies using 95%+ of budget.
    """
    repo = ContextAssemblyLogRepository(db)
    logs = await repo.get_budget_utilization(project_id, threshold=threshold)

    return [
        ContextAssemblyLogResponse(
            id=log.id,
            task_id=log.task_id,
            project_id=str(log.project_id),
            sources_queried=log.sources_queried,
            candidates_found=log.candidates_found,
            items_included=log.items_included,
            tokens_used=log.tokens_used,
            tokens_budget=log.tokens_budget,
            compression_applied=log.compression_applied,
            compression_ratio=log.compression_ratio,
            stages_applied=log.stages_applied,
            assembly_time_ms=log.assembly_time_ms,
            context_hash=log.context_hash,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/{log_id}")
async def get_context_log(
    log_id: int,
    db: Annotated[Database, Depends(get_db)],
) -> ContextAssemblyLogResponse:
    """Get a specific context assembly log entry by ID."""
    repo = ContextAssemblyLogRepository(db)
    log = await repo.get(log_id)

    if not log:
        raise HTTPException(status_code=404, detail="Context assembly log not found")

    return ContextAssemblyLogResponse(
        id=log.id,
        task_id=log.task_id,
        project_id=str(log.project_id),
        sources_queried=log.sources_queried,
        candidates_found=log.candidates_found,
        items_included=log.items_included,
        tokens_used=log.tokens_used,
        tokens_budget=log.tokens_budget,
        compression_applied=log.compression_applied,
        compression_ratio=log.compression_ratio,
        stages_applied=log.stages_applied,
        assembly_time_ms=log.assembly_time_ms,
        context_hash=log.context_hash,
        created_at=log.created_at.isoformat(),
    )


@router.delete("/cleanup")
async def cleanup_old_logs(
    db: Annotated[Database, Depends(get_db)],
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, int]:
    """Delete context assembly logs older than the specified number of days.

    Returns the number of logs deleted.
    """
    repo = ContextAssemblyLogRepository(db)
    deleted = await repo.cleanup_old(days=days)

    return {"deleted": deleted}
