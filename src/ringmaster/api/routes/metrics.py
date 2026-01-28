"""Metrics API routes for dashboard display."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database

logger = logging.getLogger(__name__)
router = APIRouter()


class TaskStats(BaseModel):
    """Task statistics by status."""

    total: int
    draft: int
    ready: int
    assigned: int
    in_progress: int
    blocked: int
    review: int
    done: int
    failed: int


class WorkerStats(BaseModel):
    """Worker statistics by status."""

    total: int
    idle: int
    busy: int
    offline: int
    total_completed: int
    total_failed: int


class RecentEvent(BaseModel):
    """Recent event from the events table."""

    id: int
    event_type: str
    entity_type: str
    entity_id: str
    data: dict | None
    created_at: str


class ActivitySummary(BaseModel):
    """Activity summary for a time period."""

    tasks_completed: int
    tasks_failed: int
    tasks_created: int


class MetricsResponse(BaseModel):
    """Complete metrics response for dashboard."""

    timestamp: str
    task_stats: TaskStats
    worker_stats: WorkerStats
    recent_events: list[RecentEvent]
    activity_24h: ActivitySummary
    activity_7d: ActivitySummary


async def get_task_stats(db: Database) -> TaskStats:
    """Get task counts grouped by status."""
    rows = await db.fetchall(
        """
        SELECT status, COUNT(*) as count
        FROM tasks
        GROUP BY status
        """
    )

    counts = {row["status"]: row["count"] for row in rows}

    return TaskStats(
        total=sum(counts.values()),
        draft=counts.get("draft", 0),
        ready=counts.get("ready", 0),
        assigned=counts.get("assigned", 0),
        in_progress=counts.get("in_progress", 0),
        blocked=counts.get("blocked", 0),
        review=counts.get("review", 0),
        done=counts.get("done", 0),
        failed=counts.get("failed", 0),
    )


async def get_worker_stats(db: Database) -> WorkerStats:
    """Get worker counts grouped by status."""
    rows = await db.fetchall(
        """
        SELECT status, COUNT(*) as count
        FROM workers
        GROUP BY status
        """
    )

    counts = {row["status"]: row["count"] for row in rows}

    # Get aggregate completion stats
    totals = await db.fetchone(
        """
        SELECT
            COALESCE(SUM(tasks_completed), 0) as completed,
            COALESCE(SUM(tasks_failed), 0) as failed
        FROM workers
        """
    )

    return WorkerStats(
        total=sum(counts.values()),
        idle=counts.get("idle", 0),
        busy=counts.get("busy", 0),
        offline=counts.get("offline", 0),
        total_completed=totals["completed"] if totals else 0,
        total_failed=totals["failed"] if totals else 0,
    )


async def get_recent_events(db: Database, limit: int = 20) -> list[RecentEvent]:
    """Get recent events from the events table."""
    rows = await db.fetchall(
        """
        SELECT id, event_type, entity_type, entity_id, data, created_at
        FROM events
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    events = []
    for row in rows:
        data = None
        if row["data"]:
            try:
                data = json.loads(row["data"])
            except json.JSONDecodeError:
                data = {"raw": row["data"]}

        events.append(
            RecentEvent(
                id=row["id"],
                event_type=row["event_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                data=data,
                created_at=row["created_at"],
            )
        )

    return events


async def get_activity_summary(db: Database, hours: int) -> ActivitySummary:
    """Get activity summary for the specified time period."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()

    # Tasks completed in period
    completed = await db.fetchone(
        """
        SELECT COUNT(*) as count FROM tasks
        WHERE status = 'done' AND completed_at >= ?
        """,
        (cutoff_str,),
    )

    # Tasks failed in period
    failed = await db.fetchone(
        """
        SELECT COUNT(*) as count FROM tasks
        WHERE status = 'failed' AND updated_at >= ?
        """,
        (cutoff_str,),
    )

    # Tasks created in period
    created = await db.fetchone(
        """
        SELECT COUNT(*) as count FROM tasks
        WHERE created_at >= ?
        """,
        (cutoff_str,),
    )

    return ActivitySummary(
        tasks_completed=completed["count"] if completed else 0,
        tasks_failed=failed["count"] if failed else 0,
        tasks_created=created["count"] if created else 0,
    )


@router.get("")
async def get_metrics(
    db: Annotated[Database, Depends(get_db)],
    event_limit: int = Query(default=20, ge=1, le=100),
) -> MetricsResponse:
    """Get comprehensive metrics for the dashboard.

    Returns task stats, worker stats, recent events, and activity summaries.
    """
    logger.info(f"Getting dashboard metrics: event_limit={event_limit}")

    task_stats = await get_task_stats(db)
    worker_stats = await get_worker_stats(db)
    recent_events = await get_recent_events(db, limit=event_limit)
    activity_24h = await get_activity_summary(db, hours=24)
    activity_7d = await get_activity_summary(db, hours=24 * 7)

    logger.info(f"Dashboard metrics retrieved: tasks_total={task_stats.total}, workers_total={worker_stats.total}, events_count={len(recent_events)}, activity_24h_completed={activity_24h.tasks_completed}")

    return MetricsResponse(
        timestamp=datetime.now(UTC).isoformat(),
        task_stats=task_stats,
        worker_stats=worker_stats,
        recent_events=recent_events,
        activity_24h=activity_24h,
        activity_7d=activity_7d,
    )


@router.get("/tasks")
async def get_task_metrics(
    db: Annotated[Database, Depends(get_db)],
) -> TaskStats:
    """Get task statistics only."""
    logger.info("Getting task statistics")

    task_stats = await get_task_stats(db)
    logger.info(f"Task stats retrieved: total={task_stats.total}, ready={task_stats.ready}, in_progress={task_stats.in_progress}, done={task_stats.done}")

    return task_stats


@router.get("/workers")
async def get_worker_metrics(
    db: Annotated[Database, Depends(get_db)],
) -> WorkerStats:
    """Get worker statistics only."""
    logger.info("Getting worker statistics")

    worker_stats = await get_worker_stats(db)
    logger.info(f"Worker stats retrieved: total={worker_stats.total}, idle={worker_stats.idle}, busy={worker_stats.busy}, completed={worker_stats.total_completed}")

    return worker_stats


@router.get("/events")
async def get_events(
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
) -> list[RecentEvent]:
    """Get recent events with optional filtering."""
    filter_info = []
    if event_type:
        filter_info.append(f"event_type={event_type}")
    if entity_type:
        filter_info.append(f"entity_type={entity_type}")
    filter_str = ", ".join(filter_info) if filter_info else "no filters"

    logger.info(f"Getting events: limit={limit}, {filter_str}")

    query = "SELECT id, event_type, entity_type, entity_id, data, created_at FROM events"
    conditions = []
    params: list = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = await db.fetchall(query, tuple(params))

    events = []
    for row in rows:
        data = None
        if row["data"]:
            try:
                data = json.loads(row["data"])
            except json.JSONDecodeError:
                data = {"raw": row["data"]}

        events.append(
            RecentEvent(
                id=row["id"],
                event_type=row["event_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                data=data,
                created_at=row["created_at"],
            )
        )

    logger.info(f"Events retrieved: count={len(events)}")

    return events


@router.get("/activity")
async def get_activity(
    db: Annotated[Database, Depends(get_db)],
    hours: int = Query(default=24, ge=1, le=720),  # Max 30 days
) -> ActivitySummary:
    """Get activity summary for a custom time period."""
    logger.info(f"Getting activity summary: hours={hours}")

    activity = await get_activity_summary(db, hours=hours)
    logger.info(f"Activity summary retrieved: completed={activity.tasks_completed}, failed={activity.tasks_failed}, created={activity.tasks_created}")

    return activity
