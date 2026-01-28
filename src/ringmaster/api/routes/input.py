"""User input API routes for natural language task creation."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ringmaster.api.deps import get_db
from ringmaster.creator import BeadCreator
from ringmaster.db import Database
from ringmaster.domain import Epic, Priority, Subtask

logger = logging.getLogger(__name__)
router = APIRouter()


class UserInputRequest(BaseModel):
    """Request body for user input submission."""

    project_id: UUID
    text: str = Field(..., min_length=1, max_length=10000)
    priority: Priority = Priority.P2
    auto_decompose: bool = True


class RelatedTaskInfo(BaseModel):
    """Information about a related task."""

    task_id: str
    title: str
    similarity: float


class CreatedTaskInfo(BaseModel):
    """Information about a created task."""

    task_id: str
    title: str
    task_type: str
    was_updated: bool = False
    matched_task_id: str | None = None


class UserInputResponse(BaseModel):
    """Response from user input submission."""

    success: bool
    epic_id: str | None = None
    created_tasks: list[CreatedTaskInfo] = []
    dependencies_count: int = 0
    messages: list[str] = []


class SuggestRelatedRequest(BaseModel):
    """Request body for suggesting related tasks."""

    project_id: UUID
    text: str = Field(..., min_length=1, max_length=10000)
    max_results: int = Field(default=5, ge=1, le=20)


class SuggestRelatedResponse(BaseModel):
    """Response for related task suggestions."""

    related_tasks: list[RelatedTaskInfo] = []


@router.post("", response_model=UserInputResponse)
async def submit_input(
    db: Annotated[Database, Depends(get_db)],
    body: UserInputRequest,
) -> UserInputResponse:
    """Submit natural language input to create tasks.

    The bead-creator service will:
    1. Parse the input to extract actionable items
    2. Check for existing matching tasks (to update instead of duplicate)
    3. Decompose large tasks into smaller subtasks
    4. Create dependencies based on ordering
    5. Return the created/updated tasks
    """
    logger.info(f"Submitting input for project {body.project_id}: text_length={len(body.text)}, priority={body.priority}, auto_decompose={body.auto_decompose}")

    creator = BeadCreator(
        db=db,
        auto_decompose=body.auto_decompose,
    )

    result = await creator.create_from_input(
        project_id=body.project_id,
        text=body.text,
        priority=body.priority,
    )

    created_tasks: list[CreatedTaskInfo] = []
    updated_count = 0
    new_count = 0

    for ct in result.created_tasks:
        task_type = "task"
        if isinstance(ct.task, Epic):
            task_type = "epic"
        elif isinstance(ct.task, Subtask):
            task_type = "subtask"

        if ct.was_updated:
            updated_count += 1
        else:
            new_count += 1

        created_tasks.append(
            CreatedTaskInfo(
                task_id=ct.task.id,
                title=ct.task.title,
                task_type=task_type,
                was_updated=ct.was_updated,
                matched_task_id=ct.matched_task_id,
            )
        )

    response = UserInputResponse(
        success=len(result.created_tasks) > 0 or result.epic is not None,
        epic_id=result.epic.id if result.epic else None,
        created_tasks=created_tasks,
        dependencies_count=len(result.dependencies_created),
        messages=result.messages,
    )

    logger.info(f"Input processing complete for project {body.project_id}: "
               f"created_tasks={len(created_tasks)} (new={new_count}, updated={updated_count}), "
               f"epic_id={response.epic_id}, dependencies={response.dependencies_count}")

    return response


@router.post("/suggest-related", response_model=SuggestRelatedResponse)
async def suggest_related(
    db: Annotated[Database, Depends(get_db)],
    body: SuggestRelatedRequest,
) -> SuggestRelatedResponse:
    """Find existing tasks related to the input text.

    Use this before creating tasks to check for potential duplicates
    or to understand what related work already exists.
    """
    logger.info(f"Suggesting related tasks for project {body.project_id}: text_length={len(body.text)}, max_results={body.max_results}")

    creator = BeadCreator(db=db)

    related = await creator.suggest_related(
        project_id=body.project_id,
        text=body.text,
        max_results=body.max_results,
    )

    response = SuggestRelatedResponse(
        related_tasks=[
            RelatedTaskInfo(
                task_id=task.id,
                title=task.title,
                similarity=score,
            )
            for task, score in related
        ]
    )

    logger.info(f"Found {len(response.related_tasks)} related tasks for project {body.project_id}")

    return response
