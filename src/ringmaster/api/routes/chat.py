"""Chat API routes for message storage and RLM context enrichment."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import ChatRepository, Database
from ringmaster.domain import ChatMessage, Summary
from ringmaster.enricher.rlm import (
    CompressionConfig,
    RLMSummarizer,
)
from ringmaster.events import EventType, event_bus

router = APIRouter()


class MessageCreate(BaseModel):
    """Request body for creating a chat message."""

    project_id: UUID
    task_id: str | None = None
    role: str  # user, assistant, system
    content: str
    media_type: str | None = None
    media_path: str | None = None
    token_count: int | None = None


class HistoryContextRequest(BaseModel):
    """Request body for getting compressed history context."""

    task_id: str | None = None
    recent_verbatim: int = 10
    summary_threshold: int = 20
    chunk_size: int = 10
    max_context_tokens: int = 4000


class HistoryContextResponse(BaseModel):
    """Response containing compressed history context."""

    recent_messages: list[ChatMessage]
    summaries: list[Summary]
    key_decisions: list[str]
    total_messages: int
    estimated_tokens: int
    formatted_prompt: str


@router.get("/projects/{project_id}/messages")
async def list_messages(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    task_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    since_id: int | None = Query(default=None),
) -> list[ChatMessage]:
    """List chat messages for a project, optionally filtered by task."""
    repo = ChatRepository(db)
    return await repo.get_messages(
        project_id=project_id,
        task_id=task_id,
        limit=limit,
        offset=offset,
        since_id=since_id,
    )


@router.post("/projects/{project_id}/messages", status_code=201)
async def create_message(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    body: MessageCreate,
) -> ChatMessage:
    """Create a new chat message."""
    if body.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail="project_id in body must match URL",
        )

    repo = ChatRepository(db)
    message = ChatMessage(
        project_id=body.project_id,
        task_id=body.task_id,
        role=body.role,
        content=body.content,
        media_type=body.media_type,
        media_path=body.media_path,
        token_count=body.token_count,
    )
    created = await repo.create_message(message)

    # Emit event for real-time updates
    await event_bus.emit(
        EventType.MESSAGE_CREATED,
        data={
            "message_id": created.id,
            "role": created.role,
            "content": created.content,
            "task_id": created.task_id,
            "created_at": created.created_at.isoformat() if created.created_at else None,
        },
        project_id=str(project_id),
    )

    return created


@router.get("/projects/{project_id}/messages/recent")
async def get_recent_messages(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    count: int = Query(default=10, ge=1, le=100),
    task_id: str | None = Query(default=None),
) -> list[ChatMessage]:
    """Get the most recent N messages for a project/task."""
    repo = ChatRepository(db)
    return await repo.get_recent_messages(
        project_id=project_id,
        count=count,
        task_id=task_id,
    )


@router.get("/projects/{project_id}/messages/count")
async def get_message_count(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    task_id: str | None = Query(default=None),
) -> dict[str, int]:
    """Get total message count for a project/task."""
    repo = ChatRepository(db)
    count = await repo.get_message_count(project_id=project_id, task_id=task_id)
    return {"count": count}


@router.get("/projects/{project_id}/summaries")
async def list_summaries(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    task_id: str | None = Query(default=None),
) -> list[Summary]:
    """List all RLM summaries for a project/task."""
    repo = ChatRepository(db)
    return await repo.get_summaries(project_id=project_id, task_id=task_id)


@router.get("/projects/{project_id}/summaries/latest")
async def get_latest_summary(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    task_id: str | None = Query(default=None),
) -> Summary:
    """Get the most recent RLM summary for a project/task."""
    repo = ChatRepository(db)
    summary = await repo.get_latest_summary(project_id=project_id, task_id=task_id)
    if not summary:
        raise HTTPException(status_code=404, detail="No summaries found")
    return summary


@router.post("/projects/{project_id}/context")
async def get_history_context(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    body: HistoryContextRequest | None = None,
) -> HistoryContextResponse:
    """Get compressed history context for RLM enrichment.

    This endpoint assembles context from chat history using the RLM algorithm:
    - Recent messages are kept verbatim
    - Older messages are summarized in chunks
    - Key decisions are extracted and preserved
    """
    body = body or HistoryContextRequest()

    config = CompressionConfig(
        recent_verbatim=body.recent_verbatim,
        summary_threshold=body.summary_threshold,
        chunk_size=body.chunk_size,
        max_context_tokens=body.max_context_tokens,
    )

    summarizer = RLMSummarizer(db, config)
    context = await summarizer.get_history_context(
        project_id=project_id,
        task_id=body.task_id,
    )

    # Format for prompt inclusion
    formatted = summarizer.format_for_prompt(context)

    return HistoryContextResponse(
        recent_messages=context.recent_messages,
        summaries=context.summaries,
        key_decisions=context.key_decisions,
        total_messages=context.total_messages,
        estimated_tokens=context.estimated_tokens,
        formatted_prompt=formatted,
    )


@router.delete("/projects/{project_id}/summaries")
async def clear_summaries(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    after_id: int = Query(default=0, ge=0),
) -> dict[str, int]:
    """Delete summaries after a given message ID.

    Useful when messages are invalidated and need to be re-summarized.
    Pass after_id=0 to clear all summaries.
    """
    repo = ChatRepository(db)
    deleted = await repo.delete_summaries_after(project_id=project_id, start_id=after_id)
    return {"deleted": deleted}
