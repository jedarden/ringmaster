"""API routes for task outcomes (reasoning bank).

Per docs/08-open-architecture.md "Reflexion-Based Learning" section:
Provides access to task execution outcomes for analysis and learning.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ringmaster.api.deps import get_db
from ringmaster.db import Database
from ringmaster.db.repositories import ReasoningBankRepository

logger = logging.getLogger(__name__)
router = APIRouter()


class TaskOutcomeResponse(BaseModel):
    """Response model for a task outcome."""

    id: int
    task_id: str
    project_id: str
    file_count: int
    keywords: list[str]
    bead_type: str
    has_dependencies: bool
    model_used: str
    worker_type: str | None
    iterations: int
    duration_seconds: int
    success: bool
    outcome: str | None
    confidence: float
    failure_reason: str | None
    reflection: str | None
    created_at: str


class SimilarOutcomeResponse(BaseModel):
    """Response model for similar outcome with similarity score."""

    outcome: TaskOutcomeResponse
    similarity: float


class ModelSuccessRateResponse(BaseModel):
    """Response model for model success rate statistics."""

    model_used: str
    total: int
    success: int
    success_rate: float
    avg_iterations: float
    avg_duration_seconds: float


class OutcomeStatsResponse(BaseModel):
    """Response model for overall outcome statistics."""

    total_outcomes: int
    success_count: int
    success_rate: float
    avg_iterations: float
    avg_duration_seconds: float
    avg_confidence: float


class FindSimilarRequest(BaseModel):
    """Request model for finding similar outcomes."""

    keywords: list[str]
    bead_type: str
    file_count: int | None = None
    min_similarity: float = Field(default=0.3, ge=0.0, le=1.0)
    project_id: str | None = None


@router.get("/outcomes", response_model=list[TaskOutcomeResponse])
async def list_outcomes(
    project_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
) -> list[TaskOutcomeResponse]:
    """List task outcomes from the reasoning bank.

    Optionally filter by project.
    """
    if project_id:
        logger.info(f"Getting outcomes for project {project_id} (limit={limit}, offset={offset})")
    else:
        logger.info(f"Getting all outcomes (limit={limit}, offset={offset})")

    repo = ReasoningBankRepository(db)

    if project_id:
        outcomes = await repo.list_for_project(project_id, limit=limit, offset=offset)
    else:
        # List all outcomes (recent first)
        rows = await db.fetchall(
            """
            SELECT * FROM task_outcomes
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        outcomes = [repo._row_to_outcome(row) for row in rows]

    logger.info(f"Found {len(outcomes)} outcomes")
    return [
        TaskOutcomeResponse(
            id=o.id or 0,
            task_id=o.task_id,
            project_id=str(o.project_id),
            file_count=o.file_count,
            keywords=o.keywords,
            bead_type=o.bead_type,
            has_dependencies=o.has_dependencies,
            model_used=o.model_used,
            worker_type=o.worker_type,
            iterations=o.iterations,
            duration_seconds=o.duration_seconds,
            success=o.success,
            outcome=o.outcome,
            confidence=o.confidence,
            failure_reason=o.failure_reason,
            reflection=o.reflection,
            created_at=o.created_at.isoformat(),
        )
        for o in outcomes
    ]


@router.get("/outcomes/{outcome_id}", response_model=TaskOutcomeResponse)
async def get_outcome(
    outcome_id: int,
    db: Database = Depends(get_db),
) -> TaskOutcomeResponse:
    """Get a specific task outcome by ID."""
    logger.info(f"Getting outcome {outcome_id}")
    repo = ReasoningBankRepository(db)
    outcome = await repo.get(outcome_id)

    if not outcome:
        logger.warning(f"Outcome {outcome_id} not found")
        raise HTTPException(status_code=404, detail="Outcome not found")

    logger.info(f"Retrieved outcome {outcome_id} for task {outcome.task_id}")
    return TaskOutcomeResponse(
        id=outcome.id or 0,
        task_id=outcome.task_id,
        project_id=str(outcome.project_id),
        file_count=outcome.file_count,
        keywords=outcome.keywords,
        bead_type=outcome.bead_type,
        has_dependencies=outcome.has_dependencies,
        model_used=outcome.model_used,
        worker_type=outcome.worker_type,
        iterations=outcome.iterations,
        duration_seconds=outcome.duration_seconds,
        success=outcome.success,
        outcome=outcome.outcome,
        confidence=outcome.confidence,
        failure_reason=outcome.failure_reason,
        reflection=outcome.reflection,
        created_at=outcome.created_at.isoformat(),
    )


@router.get("/outcomes/for-task/{task_id}", response_model=TaskOutcomeResponse | None)
async def get_outcome_for_task(
    task_id: str,
    db: Database = Depends(get_db),
) -> TaskOutcomeResponse | None:
    """Get the outcome for a specific task."""
    logger.info(f"Getting outcome for task {task_id}")
    repo = ReasoningBankRepository(db)
    outcome = await repo.get_for_task(task_id)

    if not outcome:
        logger.info(f"No outcome found for task {task_id}")
        return None

    logger.info(f"Retrieved outcome for task {task_id} (outcome_id={outcome.id})")
    return TaskOutcomeResponse(
        id=outcome.id or 0,
        task_id=outcome.task_id,
        project_id=str(outcome.project_id),
        file_count=outcome.file_count,
        keywords=outcome.keywords,
        bead_type=outcome.bead_type,
        has_dependencies=outcome.has_dependencies,
        model_used=outcome.model_used,
        worker_type=outcome.worker_type,
        iterations=outcome.iterations,
        duration_seconds=outcome.duration_seconds,
        success=outcome.success,
        outcome=outcome.outcome,
        confidence=outcome.confidence,
        failure_reason=outcome.failure_reason,
        reflection=outcome.reflection,
        created_at=outcome.created_at.isoformat(),
    )


@router.post("/outcomes/find-similar", response_model=list[SimilarOutcomeResponse])
async def find_similar_outcomes(
    request: FindSimilarRequest,
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> list[SimilarOutcomeResponse]:
    """Find similar past task outcomes for learning.

    Uses keyword-based Jaccard similarity to find related tasks
    from the reasoning bank.
    """
    logger.info(f"Finding similar outcomes: bead_type={request.bead_type}, "
                f"keywords={request.keywords}, min_similarity={request.min_similarity}, "
                f"project_id={request.project_id}, limit={limit}")

    repo = ReasoningBankRepository(db)

    project_uuid = UUID(request.project_id) if request.project_id else None

    similar = await repo.find_similar(
        keywords=request.keywords,
        bead_type=request.bead_type,
        file_count=request.file_count,
        min_similarity=request.min_similarity,
        limit=limit,
        project_id=project_uuid,
    )

    logger.info(f"Found {len(similar)} similar outcomes")
    return [
        SimilarOutcomeResponse(
            outcome=TaskOutcomeResponse(
                id=o.id or 0,
                task_id=o.task_id,
                project_id=str(o.project_id),
                file_count=o.file_count,
                keywords=o.keywords,
                bead_type=o.bead_type,
                has_dependencies=o.has_dependencies,
                model_used=o.model_used,
                worker_type=o.worker_type,
                iterations=o.iterations,
                duration_seconds=o.duration_seconds,
                success=o.success,
                outcome=o.outcome,
                confidence=o.confidence,
                failure_reason=o.failure_reason,
                reflection=o.reflection,
                created_at=o.created_at.isoformat(),
            ),
            similarity=score,
        )
        for o, score in similar
    ]


@router.get("/outcomes/model-stats", response_model=list[ModelSuccessRateResponse])
async def get_model_success_rates(
    bead_type: str | None = None,
    project_id: UUID | None = None,
    min_samples: int = Query(3, ge=1),
    db: Database = Depends(get_db),
) -> list[ModelSuccessRateResponse]:
    """Get success rates per model from the reasoning bank.

    Useful for understanding which models perform best for
    different task types.
    """
    logger.info(f"Getting model success rates: bead_type={bead_type}, "
                f"project_id={project_id}, min_samples={min_samples}")

    repo = ReasoningBankRepository(db)

    rates = await repo.get_model_success_rates(
        bead_type=bead_type,
        project_id=project_id,
        min_samples=min_samples,
    )

    logger.info(f"Retrieved success rates for {len(rates)} models")
    return [
        ModelSuccessRateResponse(
            model_used=model,
            total=stats["total"],
            success=stats["success"],
            success_rate=stats["success_rate"],
            avg_iterations=stats["avg_iterations"],
            avg_duration_seconds=stats["avg_duration_seconds"],
        )
        for model, stats in rates.items()
    ]


@router.get("/outcomes/stats", response_model=OutcomeStatsResponse)
async def get_outcome_stats(
    project_id: UUID | None = None,
    db: Database = Depends(get_db),
) -> OutcomeStatsResponse:
    """Get aggregated statistics for the reasoning bank."""
    if project_id:
        logger.info(f"Getting outcome stats for project {project_id}")
    else:
        logger.info("Getting overall outcome stats")

    repo = ReasoningBankRepository(db)
    stats = await repo.get_stats(project_id)

    logger.info(f"Retrieved outcome stats: total={stats['total_outcomes']}, "
                f"success_rate={stats['success_rate']:.2f}")
    return OutcomeStatsResponse(
        total_outcomes=stats["total_outcomes"],
        success_count=stats["success_count"],
        success_rate=stats["success_rate"],
        avg_iterations=stats["avg_iterations"],
        avg_duration_seconds=stats["avg_duration_seconds"],
        avg_confidence=stats["avg_confidence"],
    )


@router.delete("/outcomes/cleanup")
async def cleanup_old_outcomes(
    days: int = Query(90, ge=1, le=365),
    db: Database = Depends(get_db),
) -> dict:
    """Delete task outcomes older than the specified number of days.

    Default is 90 days to keep learning data reasonably fresh.
    """
    logger.info(f"Cleaning up outcomes older than {days} days")
    repo = ReasoningBankRepository(db)
    deleted = await repo.cleanup_old(days)
    logger.info(f"Cleanup completed: deleted {deleted} old outcomes")
    return {"deleted": deleted, "days": days}
