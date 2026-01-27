"""Decision and Question API routes.

Provides endpoints for human-in-the-loop decision points and clarification questions.
- Decisions: Block task progress until resolved
- Questions: Non-blocking clarification requests
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, TaskRepository
from ringmaster.domain import Decision, Question, TaskStatus
from ringmaster.events import EventType, event_bus

router = APIRouter()


# --- Request/Response Models ---


class DecisionCreate(BaseModel):
    """Request body for creating a decision."""

    project_id: UUID
    blocks_id: str  # Task ID that this decision blocks
    question: str
    context: str | None = None
    options: list[str] = []
    recommendation: str | None = None


class DecisionResolve(BaseModel):
    """Request body for resolving a decision."""

    resolution: str  # The chosen option or answer


class QuestionCreate(BaseModel):
    """Request body for creating a question."""

    project_id: UUID
    related_id: str  # Task ID this question relates to
    question: str
    urgency: str = "medium"  # low, medium, high
    default_answer: str | None = None


class QuestionAnswer(BaseModel):
    """Request body for answering a question."""

    answer: str


class DecisionStats(BaseModel):
    """Statistics about decisions for a project."""

    total: int
    pending: int
    resolved: int


class QuestionStats(BaseModel):
    """Statistics about questions for a project."""

    total: int
    pending: int
    answered: int
    by_urgency: dict[str, int]


# --- Decision Endpoints ---


@router.get("/decisions")
async def list_decisions(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = None,
    blocks_id: str | None = None,
    pending_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Decision]:
    """List decisions with optional filters.

    Args:
        project_id: Filter by project
        blocks_id: Filter by blocked task ID
        pending_only: If True, only return unresolved decisions
        limit: Maximum number of results
        offset: Pagination offset
    """
    repo = TaskRepository(db)
    return await repo.list_decisions(
        project_id=project_id,
        blocks_id=blocks_id,
        pending_only=pending_only,
        limit=limit,
        offset=offset,
    )


@router.post("/decisions", status_code=201)
async def create_decision(
    db: Annotated[Database, Depends(get_db)],
    body: DecisionCreate,
) -> Decision:
    """Create a new decision that blocks a task.

    When a worker encounters a situation requiring human input,
    it creates a decision that blocks the task until resolved.
    """
    repo = TaskRepository(db)

    # Verify the blocked task exists
    blocked_task = await repo.get_task(body.blocks_id)
    if not blocked_task:
        raise HTTPException(status_code=404, detail="Blocked task not found")

    # Create the decision
    decision = Decision(
        blocks_id=body.blocks_id,
        question=body.question,
        context=body.context,
        options=body.options,
        recommendation=body.recommendation,
    )
    created = await repo.create_decision(decision, body.project_id)

    # Mark the blocked task as BLOCKED
    blocked_task.status = TaskStatus.BLOCKED
    blocked_task.blocked_reason = body.question
    await repo.update_task(blocked_task)

    # Emit events
    await event_bus.emit(
        EventType.DECISION_CREATED,
        data={
            "decision_id": created.id,
            "blocks_id": body.blocks_id,
            "question": body.question,
            "options": body.options,
        },
        project_id=str(body.project_id),
    )

    return created


@router.get("/decisions/{decision_id}")
async def get_decision(
    db: Annotated[Database, Depends(get_db)],
    decision_id: str,
) -> Decision:
    """Get a decision by ID."""
    repo = TaskRepository(db)
    decision = await repo.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision


@router.post("/decisions/{decision_id}/resolve")
async def resolve_decision(
    db: Annotated[Database, Depends(get_db)],
    decision_id: str,
    body: DecisionResolve,
) -> Decision:
    """Resolve a decision with the chosen option.

    This unblocks the associated task and allows work to continue.
    """
    repo = TaskRepository(db)

    # Get the decision first to find the blocked task
    decision = await repo.get_decision(decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    if decision.resolution:
        raise HTTPException(status_code=400, detail="Decision already resolved")

    # Resolve the decision
    resolved = await repo.resolve_decision(decision_id, body.resolution)
    if not resolved:
        raise HTTPException(status_code=400, detail="Failed to resolve decision")

    # Unblock the task
    blocked_task = await repo.get_task(decision.blocks_id)
    if blocked_task and blocked_task.status == TaskStatus.BLOCKED:
        blocked_task.status = TaskStatus.READY
        blocked_task.blocked_reason = None
        await repo.update_task(blocked_task)

        # Emit task unblocked event
        await event_bus.emit(
            EventType.TASK_UPDATED,
            data={
                "task_id": blocked_task.id,
                "status": "ready",
                "unblocked_by": decision_id,
            },
            project_id=str(blocked_task.project_id),
        )

    # Emit decision resolved event
    # Get project_id from blocked task or use a query
    project_id = str(blocked_task.project_id) if blocked_task else None
    await event_bus.emit(
        EventType.DECISION_RESOLVED,
        data={
            "decision_id": decision_id,
            "resolution": body.resolution,
            "blocks_id": decision.blocks_id,
        },
        project_id=project_id,
    )

    return resolved


@router.get("/decisions/for-task/{task_id}")
async def get_decisions_for_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    pending_only: bool = Query(default=False),
) -> list[Decision]:
    """Get all decisions blocking a specific task."""
    repo = TaskRepository(db)
    return await repo.list_decisions(blocks_id=task_id, pending_only=pending_only)


@router.get("/projects/{project_id}/decisions/stats")
async def get_decision_stats(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> DecisionStats:
    """Get decision statistics for a project."""
    repo = TaskRepository(db)
    all_decisions = await repo.list_decisions(project_id=project_id, pending_only=False)
    pending = [d for d in all_decisions if d.resolution is None]

    return DecisionStats(
        total=len(all_decisions),
        pending=len(pending),
        resolved=len(all_decisions) - len(pending),
    )


# --- Question Endpoints ---


@router.get("/questions")
async def list_questions(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID | None = None,
    related_id: str | None = None,
    pending_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Question]:
    """List questions with optional filters.

    Args:
        project_id: Filter by project
        related_id: Filter by related task ID
        pending_only: If True, only return unanswered questions
        limit: Maximum number of results
        offset: Pagination offset
    """
    repo = TaskRepository(db)
    return await repo.list_questions(
        project_id=project_id,
        related_id=related_id,
        pending_only=pending_only,
        limit=limit,
        offset=offset,
    )


@router.post("/questions", status_code=201)
async def create_question(
    db: Annotated[Database, Depends(get_db)],
    body: QuestionCreate,
) -> Question:
    """Create a new clarification question.

    Questions are non-blocking - work can continue with default assumptions.
    """
    repo = TaskRepository(db)

    # Verify the related task exists
    related_task = await repo.get_task(body.related_id)
    if not related_task:
        raise HTTPException(status_code=404, detail="Related task not found")

    # Create the question
    question = Question(
        related_id=body.related_id,
        question=body.question,
        urgency=body.urgency,
        default_answer=body.default_answer,
    )
    created = await repo.create_question(question, body.project_id)

    # Emit event
    await event_bus.emit(
        EventType.QUESTION_CREATED,
        data={
            "question_id": created.id,
            "related_id": body.related_id,
            "question": body.question,
            "urgency": body.urgency,
        },
        project_id=str(body.project_id),
    )

    return created


@router.get("/questions/{question_id}")
async def get_question(
    db: Annotated[Database, Depends(get_db)],
    question_id: str,
) -> Question:
    """Get a question by ID."""
    repo = TaskRepository(db)
    question = await repo.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.post("/questions/{question_id}/answer")
async def answer_question(
    db: Annotated[Database, Depends(get_db)],
    question_id: str,
    body: QuestionAnswer,
) -> Question:
    """Answer a question."""
    repo = TaskRepository(db)

    # Get the question first
    question = await repo.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.answer:
        raise HTTPException(status_code=400, detail="Question already answered")

    # Answer the question
    answered = await repo.answer_question(question_id, body.answer)
    if not answered:
        raise HTTPException(status_code=400, detail="Failed to answer question")

    # Get related task for project_id
    related_task = await repo.get_task(question.related_id)
    project_id = str(related_task.project_id) if related_task else None

    # Emit event
    await event_bus.emit(
        EventType.QUESTION_ANSWERED,
        data={
            "question_id": question_id,
            "related_id": question.related_id,
            "answer": body.answer,
        },
        project_id=project_id,
    )

    return answered


@router.get("/questions/for-task/{task_id}")
async def get_questions_for_task(
    db: Annotated[Database, Depends(get_db)],
    task_id: str,
    pending_only: bool = Query(default=False),
) -> list[Question]:
    """Get all questions related to a specific task."""
    repo = TaskRepository(db)
    return await repo.list_questions(related_id=task_id, pending_only=pending_only)


@router.get("/projects/{project_id}/questions/stats")
async def get_question_stats(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> QuestionStats:
    """Get question statistics for a project."""
    repo = TaskRepository(db)
    all_questions = await repo.list_questions(project_id=project_id, pending_only=False)
    pending = [q for q in all_questions if q.answer is None]

    # Count by urgency
    by_urgency: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    for q in pending:
        if q.urgency in by_urgency:
            by_urgency[q.urgency] += 1

    return QuestionStats(
        total=len(all_questions),
        pending=len(pending),
        answered=len(all_questions) - len(pending),
        by_urgency=by_urgency,
    )
