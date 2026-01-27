"""Logs API routes for observability.

Based on docs/09-remaining-decisions.md section 20:
- View logs by component (api, queue, enricher, workers)
- Search logs
- Get logs relevant to a specific bead/task for debugging
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database
from ringmaster.domain.enums import LogComponent, LogLevel

router = APIRouter()


class LogEntryResponse(BaseModel):
    """Log entry response model."""

    id: int
    timestamp: str
    level: str
    component: str
    message: str
    task_id: str | None
    worker_id: str | None
    project_id: str | None
    data: dict | None


class LogEntryCreate(BaseModel):
    """Request model for creating a log entry."""

    level: LogLevel = LogLevel.INFO
    component: LogComponent
    message: str
    task_id: str | None = None
    worker_id: str | None = None
    project_id: str | None = None
    data: dict | None = None


class LogsResponse(BaseModel):
    """Response model for log listing with metadata."""

    logs: list[LogEntryResponse]
    total: int
    offset: int
    limit: int


def _row_to_log_entry(row) -> LogEntryResponse:
    """Convert database row to LogEntryResponse."""
    data = None
    if row["data"]:
        try:
            data = json.loads(row["data"])
        except json.JSONDecodeError:
            data = {"raw": row["data"]}

    return LogEntryResponse(
        id=row["id"],
        timestamp=row["timestamp"],
        level=row["level"],
        component=row["component"],
        message=row["message"],
        task_id=row["task_id"],
        worker_id=row["worker_id"],
        project_id=row["project_id"],
        data=data,
    )


@router.post("", status_code=201)
async def create_log(
    log_entry: LogEntryCreate,
    db: Annotated[Database, Depends(get_db)],
) -> LogEntryResponse:
    """Create a new log entry.

    Used by system components to write structured logs.
    """
    timestamp = datetime.now(UTC).isoformat()
    data_json = json.dumps(log_entry.data) if log_entry.data else None

    cursor = await db.execute(
        """
        INSERT INTO logs (timestamp, level, component, message, task_id, worker_id, project_id, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            log_entry.level.value,
            log_entry.component.value,
            log_entry.message,
            log_entry.task_id,
            log_entry.worker_id,
            log_entry.project_id,
            data_json,
        ),
    )
    await db.commit()

    row = await db.fetchone("SELECT * FROM logs WHERE id = ?", (cursor.lastrowid,))
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create log entry")

    return _row_to_log_entry(row)


@router.get("")
async def list_logs(
    db: Annotated[Database, Depends(get_db)],
    component: LogComponent | None = Query(default=None, description="Filter by component"),
    level: LogLevel | None = Query(default=None, description="Filter by level"),
    task_id: str | None = Query(default=None, description="Filter by task ID"),
    worker_id: str | None = Query(default=None, description="Filter by worker ID"),
    project_id: str | None = Query(default=None, description="Filter by project ID"),
    since: str | None = Query(default=None, description="ISO timestamp - show logs after this time"),
    search: str | None = Query(default=None, description="Full-text search in messages"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
) -> LogsResponse:
    """List logs with filtering and pagination.

    Supports filtering by component, level, task, worker, project, and time range.
    Full-text search is supported via the 'search' parameter.
    """
    query = "SELECT * FROM logs"
    count_query = "SELECT COUNT(*) as total FROM logs"
    conditions: list[str] = []
    params: list = []

    if component:
        conditions.append("component = ?")
        params.append(component.value)

    if level:
        conditions.append("level = ?")
        params.append(level.value)

    if task_id:
        conditions.append("task_id = ?")
        params.append(task_id)

    if worker_id:
        conditions.append("worker_id = ?")
        params.append(worker_id)

    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)

    if since:
        conditions.append("timestamp >= ?")
        params.append(since)

    if search:
        # Use FTS5 for efficient text search
        conditions.append("id IN (SELECT rowid FROM logs_fts WHERE logs_fts MATCH ?)")
        params.append(search)

    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)
        query += where_clause
        count_query += where_clause

    # Get total count
    count_row = await db.fetchone(count_query, tuple(params))
    total = count_row["total"] if count_row else 0

    # Add ordering and pagination
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = await db.fetchall(query, tuple(params))
    logs = [_row_to_log_entry(row) for row in rows]

    return LogsResponse(logs=logs, total=total, offset=offset, limit=limit)


@router.get("/recent")
async def get_recent_logs(
    db: Annotated[Database, Depends(get_db)],
    minutes: int = Query(default=60, ge=1, le=1440, description="Minutes to look back"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
) -> list[LogEntryResponse]:
    """Get recent logs from the last N minutes.

    Useful for tail-style log viewing.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    cutoff_str = cutoff.isoformat()

    rows = await db.fetchall(
        """
        SELECT * FROM logs
        WHERE timestamp >= ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (cutoff_str, limit),
    )

    return [_row_to_log_entry(row) for row in rows]


@router.get("/for-task/{task_id}")
async def get_logs_for_task(
    task_id: str,
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
) -> list[LogEntryResponse]:
    """Get all logs relevant to a specific task.

    Returns logs that directly reference this task.
    Useful for debugging task-specific issues.
    """
    # First verify the task exists
    task = await db.fetchone("SELECT id FROM tasks WHERE id = ?", (task_id,))
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    rows = await db.fetchall(
        """
        SELECT * FROM logs
        WHERE task_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (task_id, limit),
    )

    return [_row_to_log_entry(row) for row in rows]


@router.get("/for-worker/{worker_id}")
async def get_logs_for_worker(
    worker_id: str,
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
) -> list[LogEntryResponse]:
    """Get all logs for a specific worker.

    Useful for debugging worker-specific issues.
    """
    # First verify the worker exists
    worker = await db.fetchone("SELECT id FROM workers WHERE id = ?", (worker_id,))
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")

    rows = await db.fetchall(
        """
        SELECT * FROM logs
        WHERE worker_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (worker_id, limit),
    )

    return [_row_to_log_entry(row) for row in rows]


@router.get("/components")
async def get_log_components() -> list[str]:
    """Get list of available log components."""
    return [c.value for c in LogComponent]


@router.get("/levels")
async def get_log_levels() -> list[str]:
    """Get list of available log levels."""
    return [level.value for level in LogLevel]


@router.get("/stats")
async def get_log_stats(
    db: Annotated[Database, Depends(get_db)],
    hours: int = Query(default=24, ge=1, le=720, description="Hours to look back"),
) -> dict:
    """Get log statistics for the specified time period.

    Returns counts grouped by level and component.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()

    # Count by level
    level_rows = await db.fetchall(
        """
        SELECT level, COUNT(*) as count
        FROM logs
        WHERE timestamp >= ?
        GROUP BY level
        """,
        (cutoff_str,),
    )
    by_level = {row["level"]: row["count"] for row in level_rows}

    # Count by component
    component_rows = await db.fetchall(
        """
        SELECT component, COUNT(*) as count
        FROM logs
        WHERE timestamp >= ?
        GROUP BY component
        """,
        (cutoff_str,),
    )
    by_component = {row["component"]: row["count"] for row in component_rows}

    # Total count
    total_row = await db.fetchone(
        "SELECT COUNT(*) as count FROM logs WHERE timestamp >= ?",
        (cutoff_str,),
    )
    total = total_row["count"] if total_row else 0

    # Error count
    error_row = await db.fetchone(
        """
        SELECT COUNT(*) as count FROM logs
        WHERE timestamp >= ? AND level IN ('error', 'critical')
        """,
        (cutoff_str,),
    )
    errors = error_row["count"] if error_row else 0

    return {
        "period_hours": hours,
        "total": total,
        "errors": errors,
        "by_level": by_level,
        "by_component": by_component,
    }


@router.delete("")
async def clear_old_logs(
    db: Annotated[Database, Depends(get_db)],
    days: int = Query(default=7, ge=1, le=365, description="Delete logs older than N days"),
) -> dict:
    """Delete logs older than the specified number of days.

    Returns the number of logs deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    # Get count before deletion
    count_row = await db.fetchone(
        "SELECT COUNT(*) as count FROM logs WHERE timestamp < ?",
        (cutoff_str,),
    )
    count = count_row["count"] if count_row else 0

    # Delete old logs
    await db.execute("DELETE FROM logs WHERE timestamp < ?", (cutoff_str,))
    await db.commit()

    return {"deleted": count, "cutoff": cutoff_str}
