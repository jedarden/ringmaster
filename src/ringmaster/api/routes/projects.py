"""Project API routes."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import ChatRepository, Database, ProjectRepository, TaskRepository
from ringmaster.domain import Project

router = APIRouter()


class TaskStatusCounts(BaseModel):
    """Task counts by status."""

    draft: int = 0
    ready: int = 0
    assigned: int = 0
    in_progress: int = 0
    blocked: int = 0
    review: int = 0
    done: int = 0
    failed: int = 0


class LatestMessage(BaseModel):
    """Preview of the most recent message in a project."""

    content: str  # Truncated message content
    role: str  # "user", "assistant", "agent", etc.
    created_at: str  # ISO timestamp


class ProjectSummary(BaseModel):
    """Summary of a project with activity stats."""

    project: Project
    task_counts: TaskStatusCounts
    total_tasks: int
    active_workers: int
    pending_decisions: int
    pending_questions: int
    latest_activity: str | None  # ISO timestamp
    latest_message: LatestMessage | None = None  # Most recent chat message preview


class ProjectCreate(BaseModel):
    """Request body for creating a project."""

    name: str
    description: str | None = None
    tech_stack: list[str] = []
    repo_url: str | None = None


class ProjectUpdate(BaseModel):
    """Request body for updating a project."""

    name: str | None = None
    description: str | None = None
    tech_stack: list[str] | None = None
    repo_url: str | None = None


@router.get("")
async def list_projects(
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Project]:
    """List all projects."""
    repo = ProjectRepository(db)
    return await repo.list(limit=limit, offset=offset)


@router.get("/with-summaries", name="list_projects_with_summaries")
async def list_projects_with_summaries(
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="rank", description="Sort order: rank, recent, alphabetical"),
) -> list[ProjectSummary]:
    """List all projects with their summaries for the mailbox view.

    Projects are ranked by importance (default) with the following factors:
    - Pinned projects always appear first
    - Decision needed (highest priority)
    - Active agents working
    - Recent activity
    - Blocked/failed tasks

    Alternative sort options:
    - "recent": Sort by latest activity timestamp
    - "alphabetical": Sort by project name
    """
    project_repo = ProjectRepository(db)
    projects = await project_repo.list(limit=limit, offset=offset)

    summaries = []
    for project in projects:
        task_repo = TaskRepository(db)

        # Get task counts by status
        task_counts = await _get_task_counts(db, project.id)

        # Get active workers on this project
        active_workers = await _count_active_workers(db, project.id)

        # Get pending decisions
        decisions = await task_repo.list_decisions(
            project_id=project.id, pending_only=True, limit=1000
        )
        pending_decisions = len(decisions)

        # Get pending questions
        questions = await task_repo.list_questions(
            project_id=project.id, pending_only=False, limit=1000
        )
        pending_questions = len([q for q in questions if q.answer is None])

        # Get latest activity
        latest_activity = await _get_latest_activity(db, project.id)

        # Get latest message preview
        latest_message = await _get_latest_message(db, project.id)

        summaries.append(
            ProjectSummary(
                project=project,
                task_counts=task_counts,
                total_tasks=sum(
                    [
                        task_counts.draft,
                        task_counts.ready,
                        task_counts.assigned,
                        task_counts.in_progress,
                        task_counts.blocked,
                        task_counts.review,
                        task_counts.done,
                        task_counts.failed,
                    ]
                ),
                active_workers=active_workers,
                pending_decisions=pending_decisions,
                pending_questions=pending_questions,
                latest_activity=latest_activity,
                latest_message=latest_message,
            )
        )

    # Apply sorting based on sort parameter
    if sort == "rank":
        summaries = _rank_projects(summaries)
    elif sort == "recent":
        summaries = sorted(
            summaries,
            key=lambda s: (
                not s.project.pinned,  # Pinned first
                _parse_activity_timestamp(s.latest_activity),  # Most recent first
            ),
        )
    elif sort == "alphabetical":
        summaries = sorted(
            summaries,
            key=lambda s: (not s.project.pinned, s.project.name.lower()),
        )

    return summaries


@router.post("", status_code=201)
async def create_project(
    db: Annotated[Database, Depends(get_db)],
    body: ProjectCreate,
) -> Project:
    """Create a new project."""
    repo = ProjectRepository(db)
    project = Project(
        name=body.name,
        description=body.description,
        tech_stack=body.tech_stack,
        repo_url=body.repo_url,
    )
    return await repo.create(project)


@router.get("/{project_id}")
async def get_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> Project:
    """Get a project by ID."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}")
async def update_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    body: ProjectUpdate,
) -> Project:
    """Update a project."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.tech_stack is not None:
        project.tech_stack = body.tech_stack
    if body.repo_url is not None:
        project.repo_url = body.repo_url

    return await repo.update(project)


@router.post("/{project_id}/pin")
async def pin_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> Project:
    """Pin a project to the top of the mailbox."""
    repo = ProjectRepository(db)
    project = await repo.set_pinned(project_id, True)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/unpin")
async def unpin_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> Project:
    """Unpin a project from the top of the mailbox."""
    repo = ProjectRepository(db)
    project = await repo.set_pinned(project_id, False)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> None:
    """Delete a project."""
    repo = ProjectRepository(db)
    deleted = await repo.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/summary")
async def get_project_summary(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> ProjectSummary:
    """Get project summary with task/worker/decision stats."""
    project_repo = ProjectRepository(db)
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    task_repo = TaskRepository(db)

    # Get task counts by status
    task_counts = await _get_task_counts(db, project_id)

    # Get active workers on this project
    active_workers = await _count_active_workers(db, project_id)

    # Get pending decisions
    decisions = await task_repo.list_decisions(
        project_id=project_id, pending_only=True, limit=1000
    )
    pending_decisions = len(decisions)

    # Get pending questions
    questions = await task_repo.list_questions(
        project_id=project_id, pending_only=False, limit=1000
    )
    pending_questions = len([q for q in questions if q.answer is None])

    # Get latest activity
    latest_activity = await _get_latest_activity(db, project_id)

    # Get latest message preview
    latest_message = await _get_latest_message(db, project_id)

    return ProjectSummary(
        project=project,
        task_counts=task_counts,
        total_tasks=sum(
            [
                task_counts.draft,
                task_counts.ready,
                task_counts.assigned,
                task_counts.in_progress,
                task_counts.blocked,
                task_counts.review,
                task_counts.done,
                task_counts.failed,
            ]
        ),
        active_workers=active_workers,
        pending_decisions=pending_decisions,
        pending_questions=pending_questions,
        latest_activity=latest_activity,
        latest_message=latest_message,
    )


async def _get_task_counts(db: Database, project_id: UUID) -> TaskStatusCounts:
    """Get task counts by status for a project."""
    rows = await db.fetchall(
        """
        SELECT status, COUNT(*) as count
        FROM tasks
        WHERE project_id = ? AND type IN ('task', 'subtask')
        GROUP BY status
        """,
        (str(project_id),),
    )

    counts = TaskStatusCounts()
    for row in rows:
        status = row["status"]
        count = row["count"]
        if status == "draft":
            counts.draft = count
        elif status == "ready":
            counts.ready = count
        elif status == "assigned":
            counts.assigned = count
        elif status == "in_progress":
            counts.in_progress = count
        elif status == "blocked":
            counts.blocked = count
        elif status == "review":
            counts.review = count
        elif status == "done":
            counts.done = count
        elif status == "failed":
            counts.failed = count

    return counts


async def _count_active_workers(db: Database, project_id: UUID) -> int:
    """Count workers actively working on this project's tasks."""
    row = await db.fetchone(
        """
        SELECT COUNT(DISTINCT w.id) as count
        FROM workers w
        JOIN tasks t ON w.current_task_id = t.id
        WHERE t.project_id = ? AND w.status IN ('busy', 'idle')
        """,
        (str(project_id),),
    )
    return row["count"] if row else 0


async def _get_latest_activity(db: Database, project_id: UUID) -> str | None:
    """Get the latest activity timestamp for a project."""
    row = await db.fetchone(
        """
        SELECT MAX(updated_at) as latest
        FROM tasks
        WHERE project_id = ?
        """,
        (str(project_id),),
    )
    return row["latest"] if row and row["latest"] else None


async def _get_latest_message(db: Database, project_id: UUID) -> LatestMessage | None:
    """Get the most recent chat message preview for a project.

    Returns a truncated preview (max 100 chars) of the latest message.
    """
    chat_repo = ChatRepository(db)
    messages = await chat_repo.get_recent_messages(project_id, count=1)

    if not messages:
        return None

    msg = messages[0]
    # Truncate content to 100 characters
    content = msg.content
    if len(content) > 100:
        content = content[:97] + "..."

    return LatestMessage(
        content=content,
        role=msg.role,
        created_at=msg.created_at.isoformat(),
    )


def _parse_activity_timestamp(timestamp: str | None) -> float:
    """Parse activity timestamp for sorting. Returns negative for descending sort."""
    if not timestamp:
        return float("inf")  # No activity goes last
    try:
        # Handle ISO format with optional timezone
        ts = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        return -dt.timestamp()  # Negative for descending (most recent first)
    except (ValueError, TypeError):
        return float("inf")


def _rank_projects(summaries: list[ProjectSummary]) -> list[ProjectSummary]:
    """Rank projects by importance for the mailbox view.

    Ranking factors (per docs/07-user-experience.md):
    1. Pinned projects always first
    2. Decision needed (highest priority)
    3. Active agents working
    4. Blocked/failed tasks (needs attention)
    5. Recent activity
    """

    def rank_key(summary: ProjectSummary) -> tuple:
        """Generate a sorting key tuple. Lower values = higher priority."""
        # Factor 1: Pinned (pinned first)
        is_pinned = 0 if summary.project.pinned else 1

        # Factor 2: Decisions needed (more decisions = higher priority)
        # Invert so more decisions = lower value = higher priority
        decisions_score = -summary.pending_decisions

        # Factor 3: Active workers (working projects surface)
        workers_score = -summary.active_workers

        # Factor 4: Blocked or failed tasks (needs attention)
        blocked_failed = -(
            summary.task_counts.blocked + summary.task_counts.failed
        )

        # Factor 5: Questions pending (less urgent than decisions)
        questions_score = -summary.pending_questions

        # Factor 6: In-progress work (active projects)
        active_work = -(
            summary.task_counts.in_progress
            + summary.task_counts.assigned
            + summary.task_counts.review
        )

        # Factor 7: Recent activity (timestamp, more recent = higher)
        activity_time = _parse_activity_timestamp(summary.latest_activity)

        # Factor 8: Alphabetical as tiebreaker
        name = summary.project.name.lower()

        return (
            is_pinned,
            decisions_score,
            workers_score,
            blocked_failed,
            questions_score,
            active_work,
            activity_time,
            name,
        )

    return sorted(summaries, key=rank_key)
