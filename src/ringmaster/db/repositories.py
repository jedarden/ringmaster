"""Repository classes for database access."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ringmaster.db.connection import Database
from ringmaster.domain import (
    ChatMessage,
    Dependency,
    Epic,
    Priority,
    Project,
    Subtask,
    Summary,
    Task,
    TaskStatus,
    TaskType,
    Worker,
    WorkerStatus,
)


class ProjectRepository:
    """Repository for Project entities."""

    def __init__(self, db: Database):
        self.db = db

    async def create(self, project: Project) -> Project:
        """Create a new project."""
        await self.db.execute(
            """
            INSERT INTO projects (id, name, description, tech_stack, repo_url, settings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(project.id),
                project.name,
                project.description,
                json.dumps(project.tech_stack),
                project.repo_url,
                json.dumps(project.settings),
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
            ),
        )
        await self.db.commit()
        return project

    async def get(self, project_id: UUID) -> Project | None:
        """Get a project by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM projects WHERE id = ?", (str(project_id),)
        )
        if not row:
            return None
        return self._row_to_project(row)

    async def list(self, limit: int = 100, offset: int = 0) -> list[Project]:
        """List all projects."""
        rows = await self.db.fetchall(
            "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._row_to_project(row) for row in rows]

    async def update(self, project: Project) -> Project:
        """Update an existing project."""
        project.updated_at = datetime.now(UTC)
        await self.db.execute(
            """
            UPDATE projects SET
                name = ?, description = ?, tech_stack = ?, repo_url = ?, settings = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                project.name,
                project.description,
                json.dumps(project.tech_stack),
                project.repo_url,
                json.dumps(project.settings),
                project.updated_at.isoformat(),
                str(project.id),
            ),
        )
        await self.db.commit()
        return project

    async def delete(self, project_id: UUID) -> bool:
        """Delete a project."""
        cursor = await self.db.execute(
            "DELETE FROM projects WHERE id = ?", (str(project_id),)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    def _row_to_project(self, row: Any) -> Project:
        """Convert a database row to a Project."""
        return Project(
            id=UUID(row["id"]),
            name=row["name"],
            description=row["description"],
            tech_stack=json.loads(row["tech_stack"]) if row["tech_stack"] else [],
            repo_url=row["repo_url"],
            settings=json.loads(row["settings"]) if row["settings"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class TaskRepository:
    """Repository for Task entities (including Epics, Subtasks, Decisions, Questions)."""

    def __init__(self, db: Database):
        self.db = db

    async def create_task(self, task: Task | Epic | Subtask) -> Task | Epic | Subtask:
        """Create a new task."""
        await self.db.execute(
            """
            INSERT INTO tasks (
                id, project_id, parent_id, type, title, description, priority, status,
                worker_id, attempts, max_attempts, pagerank_score, betweenness_score,
                on_critical_path, combined_priority, created_at, updated_at, started_at,
                completed_at, prompt_path, output_path, context_hash, acceptance_criteria, context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                str(task.project_id),
                getattr(task, "parent_id", None),
                task.type.value,
                task.title,
                task.description,
                task.priority.value,
                task.status.value,
                getattr(task, "worker_id", None),
                getattr(task, "attempts", 0),
                getattr(task, "max_attempts", 5),
                getattr(task, "pagerank_score", 0),
                getattr(task, "betweenness_score", 0),
                getattr(task, "on_critical_path", False),
                getattr(task, "combined_priority", 0),
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
                getattr(task, "started_at", None),
                getattr(task, "completed_at", None),
                task.prompt_path,
                task.output_path,
                task.context_hash,
                json.dumps(getattr(task, "acceptance_criteria", [])),
                getattr(task, "context", None),
            ),
        )
        await self.db.commit()
        return task

    async def get_task(self, task_id: str) -> Task | Epic | Subtask | None:
        """Get a task by ID."""
        row = await self.db.fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not row:
            return None
        return self._row_to_task(row)

    async def list_tasks(
        self,
        project_id: UUID | None = None,
        parent_id: str | None = None,
        status: TaskStatus | None = None,
        task_type: TaskType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task | Epic | Subtask]:
        """List tasks with optional filters."""
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))
        if parent_id:
            conditions.append("parent_id = ?")
            params.append(parent_id)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if task_type:
            conditions.append("type = ?")
            params.append(task_type.value)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT * FROM tasks
            WHERE {where_clause}
            ORDER BY combined_priority DESC, created_at ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_task(row) for row in rows]

    async def update_task(self, task: Task | Epic | Subtask) -> Task | Epic | Subtask:
        """Update an existing task."""
        task.updated_at = datetime.now(UTC)
        await self.db.execute(
            """
            UPDATE tasks SET
                title = ?, description = ?, priority = ?, status = ?,
                worker_id = ?, attempts = ?, max_attempts = ?,
                pagerank_score = ?, betweenness_score = ?, on_critical_path = ?,
                combined_priority = ?, updated_at = ?, started_at = ?, completed_at = ?,
                prompt_path = ?, output_path = ?, context_hash = ?,
                acceptance_criteria = ?, context = ?
            WHERE id = ?
            """,
            (
                task.title,
                task.description,
                task.priority.value,
                task.status.value,
                getattr(task, "worker_id", None),
                getattr(task, "attempts", 0),
                getattr(task, "max_attempts", 5),
                getattr(task, "pagerank_score", 0),
                getattr(task, "betweenness_score", 0),
                getattr(task, "on_critical_path", False),
                getattr(task, "combined_priority", 0),
                task.updated_at.isoformat(),
                getattr(task, "started_at", None),
                getattr(task, "completed_at", None),
                task.prompt_path,
                task.output_path,
                task.context_hash,
                json.dumps(getattr(task, "acceptance_criteria", [])),
                getattr(task, "context", None),
                task.id,
            ),
        )
        await self.db.commit()
        return task

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        cursor = await self.db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await self.db.commit()
        return cursor.rowcount > 0

    async def add_dependency(self, dependency: Dependency) -> Dependency:
        """Add a dependency between tasks."""
        await self.db.execute(
            """
            INSERT OR IGNORE INTO dependencies (child_id, parent_id, created_at)
            VALUES (?, ?, ?)
            """,
            (dependency.child_id, dependency.parent_id, dependency.created_at.isoformat()),
        )
        await self.db.commit()
        return dependency

    async def get_dependencies(self, task_id: str) -> list[Dependency]:
        """Get dependencies for a task."""
        rows = await self.db.fetchall(
            "SELECT * FROM dependencies WHERE child_id = ?", (task_id,)
        )
        return [
            Dependency(
                child_id=row["child_id"],
                parent_id=row["parent_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def get_dependents(self, task_id: str) -> list[Dependency]:
        """Get tasks that depend on this task."""
        rows = await self.db.fetchall(
            "SELECT * FROM dependencies WHERE parent_id = ?", (task_id,)
        )
        return [
            Dependency(
                child_id=row["child_id"],
                parent_id=row["parent_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def get_ready_tasks(self, project_id: UUID | None = None) -> list[Task]:
        """Get tasks that are ready to be assigned (all dependencies complete)."""
        conditions = ["t.status = 'ready'", "t.type IN ('task', 'subtask')"]
        params: list[Any] = []

        if project_id:
            conditions.append("t.project_id = ?")
            params.append(str(project_id))

        query = f"""
            SELECT t.* FROM tasks t
            WHERE {' AND '.join(conditions)}
            AND NOT EXISTS (
                SELECT 1 FROM dependencies d
                JOIN tasks dep ON d.parent_id = dep.id
                WHERE d.child_id = t.id AND dep.status != 'done'
            )
            ORDER BY t.combined_priority DESC, t.created_at ASC
        """

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_task(row) for row in rows]  # type: ignore

    def _row_to_task(self, row: Any) -> Task | Epic | Subtask:
        """Convert a database row to the appropriate task type."""
        task_type = TaskType(row["type"])
        base_kwargs = {
            "id": row["id"],
            "project_id": UUID(row["project_id"]),
            "title": row["title"],
            "description": row["description"],
            "priority": Priority(row["priority"]),
            "status": TaskStatus(row["status"]),
            "created_at": datetime.fromisoformat(row["created_at"]),
            "updated_at": datetime.fromisoformat(row["updated_at"]),
            "prompt_path": row["prompt_path"],
            "output_path": row["output_path"],
            "context_hash": row["context_hash"],
        }

        if task_type == TaskType.EPIC:
            return Epic(
                **base_kwargs,
                acceptance_criteria=json.loads(row["acceptance_criteria"] or "[]"),
                context=row["context"],
            )
        elif task_type == TaskType.SUBTASK:
            return Subtask(
                **base_kwargs,
                parent_id=row["parent_id"],
                worker_id=row["worker_id"],
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
            )
        else:  # TASK
            return Task(
                **base_kwargs,
                parent_id=row["parent_id"],
                worker_id=row["worker_id"],
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                pagerank_score=row["pagerank_score"],
                betweenness_score=row["betweenness_score"],
                on_critical_path=bool(row["on_critical_path"]),
                combined_priority=row["combined_priority"],
            )


class WorkerRepository:
    """Repository for Worker entities."""

    def __init__(self, db: Database):
        self.db = db

    async def create(self, worker: Worker) -> Worker:
        """Create a new worker."""
        await self.db.execute(
            """
            INSERT INTO workers (
                id, name, type, status, current_task_id, command, args,
                prompt_flag, working_dir, timeout_seconds, env_vars,
                tasks_completed, tasks_failed, avg_completion_seconds,
                created_at, last_active_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker.id,
                worker.name,
                worker.type,
                worker.status.value,
                worker.current_task_id,
                worker.command,
                json.dumps(worker.args),
                worker.prompt_flag,
                worker.working_dir,
                worker.timeout_seconds,
                json.dumps(worker.env_vars),
                worker.tasks_completed,
                worker.tasks_failed,
                worker.avg_completion_seconds,
                worker.created_at.isoformat(),
                worker.last_active_at.isoformat() if worker.last_active_at else None,
            ),
        )
        await self.db.commit()
        return worker

    async def get(self, worker_id: str) -> Worker | None:
        """Get a worker by ID."""
        row = await self.db.fetchone("SELECT * FROM workers WHERE id = ?", (worker_id,))
        if not row:
            return None
        return self._row_to_worker(row)

    async def list(
        self,
        status: WorkerStatus | None = None,
        worker_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Worker]:
        """List workers with optional filters."""
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if worker_type:
            conditions.append("type = ?")
            params.append(worker_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT * FROM workers
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_worker(row) for row in rows]

    async def get_idle_workers(self, worker_type: str | None = None) -> list[Worker]:
        """Get workers that are idle and available for assignment."""
        conditions = ["status = 'idle'"]
        params: list[Any] = []

        if worker_type:
            conditions.append("type = ?")
            params.append(worker_type)

        query = f"""
            SELECT * FROM workers
            WHERE {' AND '.join(conditions)}
            ORDER BY tasks_completed DESC
        """

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_worker(row) for row in rows]

    async def update(self, worker: Worker) -> Worker:
        """Update an existing worker."""
        await self.db.execute(
            """
            UPDATE workers SET
                name = ?, type = ?, status = ?, current_task_id = ?,
                command = ?, args = ?, prompt_flag = ?, working_dir = ?,
                timeout_seconds = ?, env_vars = ?, tasks_completed = ?,
                tasks_failed = ?, avg_completion_seconds = ?, last_active_at = ?
            WHERE id = ?
            """,
            (
                worker.name,
                worker.type,
                worker.status.value,
                worker.current_task_id,
                worker.command,
                json.dumps(worker.args),
                worker.prompt_flag,
                worker.working_dir,
                worker.timeout_seconds,
                json.dumps(worker.env_vars),
                worker.tasks_completed,
                worker.tasks_failed,
                worker.avg_completion_seconds,
                worker.last_active_at.isoformat() if worker.last_active_at else None,
                worker.id,
            ),
        )
        await self.db.commit()
        return worker

    async def delete(self, worker_id: str) -> bool:
        """Delete a worker."""
        cursor = await self.db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        await self.db.commit()
        return cursor.rowcount > 0

    def _row_to_worker(self, row: Any) -> Worker:
        """Convert a database row to a Worker."""
        return Worker(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            status=WorkerStatus(row["status"]),
            current_task_id=row["current_task_id"],
            command=row["command"],
            args=json.loads(row["args"]) if row["args"] else [],
            prompt_flag=row["prompt_flag"],
            working_dir=row["working_dir"],
            timeout_seconds=row["timeout_seconds"],
            env_vars=json.loads(row["env_vars"]) if row["env_vars"] else {},
            tasks_completed=row["tasks_completed"],
            tasks_failed=row["tasks_failed"],
            avg_completion_seconds=row["avg_completion_seconds"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_active_at=datetime.fromisoformat(row["last_active_at"]) if row["last_active_at"] else None,
        )


class ChatRepository:
    """Repository for ChatMessage and Summary entities.

    Provides methods for storing and retrieving chat history,
    as well as RLM-compressed summaries for context enrichment.
    """

    def __init__(self, db: Database):
        self.db = db

    async def create_message(self, message: ChatMessage) -> ChatMessage:
        """Create a new chat message."""
        cursor = await self.db.execute(
            """
            INSERT INTO chat_messages (
                project_id, task_id, role, content, media_type, media_path,
                token_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(message.project_id),
                message.task_id,
                message.role,
                message.content,
                message.media_type,
                message.media_path,
                message.token_count,
                message.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        message.id = cursor.lastrowid
        return message

    async def get_messages(
        self,
        project_id: UUID,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        since_id: int | None = None,
    ) -> list[ChatMessage]:
        """Get chat messages for a project, optionally filtered by task."""
        conditions = ["project_id = ?"]
        params: list[Any] = [str(project_id)]

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        if since_id:
            conditions.append("id > ?")
            params.append(since_id)

        query = f"""
            SELECT * FROM chat_messages
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_message(row) for row in rows]

    async def get_recent_messages(
        self,
        project_id: UUID,
        count: int = 10,
        task_id: str | None = None,
    ) -> list[ChatMessage]:
        """Get the most recent N messages."""
        conditions = ["project_id = ?"]
        params: list[Any] = [str(project_id)]

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        # Get recent messages in reverse order, then reverse the result
        query = f"""
            SELECT * FROM chat_messages
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(count)

        rows = await self.db.fetchall(query, tuple(params))
        messages = [self._row_to_message(row) for row in rows]
        return list(reversed(messages))

    async def get_message_count(
        self, project_id: UUID, task_id: str | None = None
    ) -> int:
        """Get total message count for a project/task."""
        conditions = ["project_id = ?"]
        params: list[Any] = [str(project_id)]

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        query = f"""
            SELECT COUNT(*) as count FROM chat_messages
            WHERE {' AND '.join(conditions)}
        """

        row = await self.db.fetchone(query, tuple(params))
        return row["count"] if row else 0

    async def get_message_range(
        self, start_id: int, end_id: int
    ) -> list[ChatMessage]:
        """Get messages within an ID range (inclusive)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM chat_messages
            WHERE id >= ? AND id <= ?
            ORDER BY created_at ASC
            """,
            (start_id, end_id),
        )
        return [self._row_to_message(row) for row in rows]

    async def create_summary(self, summary: Summary) -> Summary:
        """Create a new RLM summary."""
        cursor = await self.db.execute(
            """
            INSERT INTO summaries (
                project_id, task_id, message_range_start, message_range_end,
                summary, key_decisions, token_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(summary.project_id),
                summary.task_id,
                summary.message_range_start,
                summary.message_range_end,
                summary.summary,
                json.dumps(summary.key_decisions),
                summary.token_count,
                summary.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        summary.id = cursor.lastrowid
        return summary

    async def get_summaries(
        self,
        project_id: UUID,
        task_id: str | None = None,
    ) -> list[Summary]:
        """Get all summaries for a project/task."""
        conditions = ["project_id = ?"]
        params: list[Any] = [str(project_id)]

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        query = f"""
            SELECT * FROM summaries
            WHERE {' AND '.join(conditions)}
            ORDER BY message_range_start ASC
        """

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_summary(row) for row in rows]

    async def get_latest_summary(
        self, project_id: UUID, task_id: str | None = None
    ) -> Summary | None:
        """Get the most recent summary."""
        conditions = ["project_id = ?"]
        params: list[Any] = [str(project_id)]

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        query = f"""
            SELECT * FROM summaries
            WHERE {' AND '.join(conditions)}
            ORDER BY message_range_end DESC
            LIMIT 1
        """

        row = await self.db.fetchone(query, tuple(params))
        return self._row_to_summary(row) if row else None

    async def delete_summaries_after(
        self, project_id: UUID, start_id: int
    ) -> int:
        """Delete summaries that cover messages after start_id.

        Used when messages are invalidated and need to be re-summarized.
        """
        cursor = await self.db.execute(
            """
            DELETE FROM summaries
            WHERE project_id = ? AND message_range_start >= ?
            """,
            (str(project_id), start_id),
        )
        await self.db.commit()
        return cursor.rowcount

    def _row_to_message(self, row: Any) -> ChatMessage:
        """Convert a database row to a ChatMessage."""
        return ChatMessage(
            id=row["id"],
            project_id=UUID(row["project_id"]),
            task_id=row["task_id"],
            role=row["role"],
            content=row["content"],
            media_type=row["media_type"],
            media_path=row["media_path"],
            token_count=row["token_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_summary(self, row: Any) -> Summary:
        """Convert a database row to a Summary."""
        return Summary(
            id=row["id"],
            project_id=UUID(row["project_id"]),
            task_id=row["task_id"],
            message_range_start=row["message_range_start"],
            message_range_end=row["message_range_end"],
            summary=row["summary"],
            key_decisions=json.loads(row["key_decisions"]) if row["key_decisions"] else [],
            token_count=row["token_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
