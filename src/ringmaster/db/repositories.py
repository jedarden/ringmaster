"""Repository classes for database access."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ringmaster.db.connection import Database
from ringmaster.domain import (
    Action,
    ActionType,
    ActorType,
    ChatMessage,
    ContextAssemblyLog,
    Decision,
    Dependency,
    EntityType,
    Epic,
    Priority,
    Project,
    Question,
    Subtask,
    Summary,
    Task,
    TaskOutcome,
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
                worker_id, attempts, max_attempts, required_capabilities, pagerank_score, betweenness_score,
                on_critical_path, combined_priority, created_at, updated_at, started_at,
                completed_at, prompt_path, output_path, context_hash, acceptance_criteria, context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(getattr(task, "required_capabilities", [])),
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

        # Handle retry_after serialization
        retry_after = getattr(task, "retry_after", None)
        retry_after_str = retry_after.isoformat() if retry_after else None

        # Handle started_at serialization
        started_at = getattr(task, "started_at", None)
        started_at_str = started_at.isoformat() if started_at else None

        # Handle completed_at serialization
        completed_at = getattr(task, "completed_at", None)
        completed_at_str = completed_at.isoformat() if completed_at else None

        await self.db.execute(
            """
            UPDATE tasks SET
                title = ?, description = ?, priority = ?, status = ?,
                worker_id = ?, attempts = ?, max_attempts = ?, required_capabilities = ?,
                pagerank_score = ?, betweenness_score = ?, on_critical_path = ?,
                combined_priority = ?, updated_at = ?, started_at = ?, completed_at = ?,
                prompt_path = ?, output_path = ?, context_hash = ?,
                acceptance_criteria = ?, context = ?,
                retry_after = ?, last_failure_reason = ?
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
                json.dumps(getattr(task, "required_capabilities", [])),
                getattr(task, "pagerank_score", 0),
                getattr(task, "betweenness_score", 0),
                getattr(task, "on_critical_path", False),
                getattr(task, "combined_priority", 0),
                task.updated_at.isoformat(),
                started_at_str,
                completed_at_str,
                task.prompt_path,
                task.output_path,
                task.context_hash,
                json.dumps(getattr(task, "acceptance_criteria", [])),
                getattr(task, "context", None),
                retry_after_str,
                getattr(task, "last_failure_reason", None),
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

    async def remove_dependency(self, child_id: str, parent_id: str) -> bool:
        """Remove a dependency between tasks."""
        cursor = await self.db.execute(
            "DELETE FROM dependencies WHERE child_id = ? AND parent_id = ?",
            (child_id, parent_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def get_ready_tasks(self, project_id: UUID | None = None) -> list[Task]:
        """Get tasks that are ready to be assigned (all dependencies complete).

        Tasks are filtered to exclude:
        - Tasks with unmet dependencies
        - Tasks where retry_after is in the future (exponential backoff)
        """
        conditions = ["t.status = 'ready'", "t.type IN ('task', 'subtask')"]
        params: list[Any] = []

        if project_id:
            conditions.append("t.project_id = ?")
            params.append(str(project_id))

        # Filter out tasks that are still in retry backoff period
        # retry_after IS NULL means no retry delay, or datetime('now') >= retry_after
        conditions.append("(t.retry_after IS NULL OR datetime('now') >= t.retry_after)")

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

        # Handle required_capabilities column - may not exist in older DBs before migration
        # Note: use row.keys() instead of 'in row' because sqlite3.Row doesn't support 'in'
        required_capabilities = []
        if "required_capabilities" in row.keys():  # noqa: SIM118
            required_capabilities = json.loads(row["required_capabilities"]) if row["required_capabilities"] else []

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

        # Handle retry tracking columns - may not exist in older DBs before migration 008
        retry_after = None
        last_failure_reason = None
        if "retry_after" in row.keys():  # noqa: SIM118
            retry_after = datetime.fromisoformat(row["retry_after"]) if row["retry_after"] else None
        if "last_failure_reason" in row.keys():  # noqa: SIM118
            last_failure_reason = row["last_failure_reason"]

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
                required_capabilities=required_capabilities,
                retry_after=retry_after,
                last_failure_reason=last_failure_reason,
            )
        else:  # TASK
            return Task(
                **base_kwargs,
                parent_id=row["parent_id"],
                worker_id=row["worker_id"],
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
                required_capabilities=required_capabilities,
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                pagerank_score=row["pagerank_score"],
                betweenness_score=row["betweenness_score"],
                on_critical_path=bool(row["on_critical_path"]),
                combined_priority=row["combined_priority"],
                retry_after=retry_after,
                last_failure_reason=last_failure_reason,
            )

    # --- Decision methods ---

    async def create_decision(self, decision: Decision, project_id: UUID) -> Decision:
        """Create a new decision that blocks a task."""
        await self.db.execute(
            """
            INSERT INTO tasks (
                id, project_id, type, title, description, status, blocks_id,
                question, options, recommendation, created_at, updated_at
            )
            VALUES (?, ?, 'decision', ?, ?, 'ready', ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                str(project_id),
                f"Decision: {decision.question[:50]}...",  # Title
                decision.context,  # Description
                decision.blocks_id,
                decision.question,
                json.dumps(decision.options),
                decision.recommendation,
                decision.created_at.isoformat(),
                decision.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        return decision

    async def get_decision(self, decision_id: str) -> Decision | None:
        """Get a decision by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM tasks WHERE id = ? AND type = 'decision'", (decision_id,)
        )
        if not row:
            return None
        return self._row_to_decision(row)

    async def list_decisions(
        self,
        project_id: UUID | None = None,
        blocks_id: str | None = None,
        pending_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Decision]:
        """List decisions with optional filters."""
        conditions = ["type = 'decision'"]
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))
        if blocks_id:
            conditions.append("blocks_id = ?")
            params.append(blocks_id)
        if pending_only:
            conditions.append("resolution IS NULL")

        query = f"""
            SELECT * FROM tasks
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_decision(row) for row in rows]

    async def resolve_decision(
        self, decision_id: str, resolution: str
    ) -> Decision | None:
        """Resolve a decision with the chosen option."""
        resolved_at = datetime.now(UTC).isoformat()
        cursor = await self.db.execute(
            """
            UPDATE tasks SET
                resolution = ?, resolved_at = ?, status = 'done', updated_at = ?
            WHERE id = ? AND type = 'decision' AND resolution IS NULL
            """,
            (resolution, resolved_at, resolved_at, decision_id),
        )
        await self.db.commit()

        if cursor.rowcount == 0:
            return None

        return await self.get_decision(decision_id)

    def _row_to_decision(self, row: Any) -> Decision:
        """Convert a database row to a Decision."""
        return Decision(
            id=row["id"],
            blocks_id=row["blocks_id"] or "",
            question=row["question"] or "",
            context=row["description"],
            options=json.loads(row["options"]) if row["options"] else [],
            recommendation=row["recommendation"],
            resolution=row["resolution"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --- Question methods ---

    async def create_question(self, question: Question, project_id: UUID) -> Question:
        """Create a new question related to a task."""
        await self.db.execute(
            """
            INSERT INTO tasks (
                id, project_id, type, title, description, status, related_id,
                question, urgency, default_answer, created_at, updated_at
            )
            VALUES (?, ?, 'question', ?, ?, 'ready', ?, ?, ?, ?, ?, ?)
            """,
            (
                question.id,
                str(project_id),
                f"Question: {question.question[:50]}...",  # Title
                None,  # Description
                question.related_id,
                question.question,
                question.urgency,
                question.default_answer,
                question.created_at.isoformat(),
                question.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        return question

    async def get_question(self, question_id: str) -> Question | None:
        """Get a question by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM tasks WHERE id = ? AND type = 'question'", (question_id,)
        )
        if not row:
            return None
        return self._row_to_question(row)

    async def list_questions(
        self,
        project_id: UUID | None = None,
        related_id: str | None = None,
        pending_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Question]:
        """List questions with optional filters."""
        conditions = ["type = 'question'"]
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))
        if related_id:
            conditions.append("related_id = ?")
            params.append(related_id)
        if pending_only:
            conditions.append("answer IS NULL")

        query = f"""
            SELECT * FROM tasks
            WHERE {' AND '.join(conditions)}
            ORDER BY
                CASE urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_question(row) for row in rows]

    async def answer_question(
        self, question_id: str, answer: str
    ) -> Question | None:
        """Answer a question."""
        answered_at = datetime.now(UTC).isoformat()
        cursor = await self.db.execute(
            """
            UPDATE tasks SET
                answer = ?, answered_at = ?, status = 'done', updated_at = ?
            WHERE id = ? AND type = 'question' AND answer IS NULL
            """,
            (answer, answered_at, answered_at, question_id),
        )
        await self.db.commit()

        if cursor.rowcount == 0:
            return None

        return await self.get_question(question_id)

    def _row_to_question(self, row: Any) -> Question:
        """Convert a database row to a Question."""
        return Question(
            id=row["id"],
            related_id=row["related_id"] or "",
            question=row["question"] or "",
            urgency=row["urgency"] or "medium",
            default_answer=row["default_answer"],
            answer=row["answer"],
            answered_at=datetime.fromisoformat(row["answered_at"]) if row["answered_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
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
                id, name, type, status, current_task_id, capabilities, command, args,
                prompt_flag, working_dir, timeout_seconds, env_vars,
                tasks_completed, tasks_failed, avg_completion_seconds,
                created_at, last_active_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker.id,
                worker.name,
                worker.type,
                worker.status.value,
                worker.current_task_id,
                json.dumps(worker.capabilities),
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
                name = ?, type = ?, status = ?, current_task_id = ?, capabilities = ?,
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
                json.dumps(worker.capabilities),
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

    async def get_capable_workers(
        self, required_capabilities: list[str], worker_type: str | None = None
    ) -> list[Worker]:
        """Get idle workers that have all the required capabilities.

        Args:
            required_capabilities: List of capabilities that workers must have.
            worker_type: Optional filter by worker type.

        Returns:
            List of workers that can handle the task (have all required capabilities).
        """
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
        workers = [self._row_to_worker(row) for row in rows]

        # Filter by capabilities (worker must have ALL required capabilities)
        if not required_capabilities:
            return workers

        capable_workers = []
        for worker in workers:
            worker_caps = set(worker.capabilities)
            if set(required_capabilities).issubset(worker_caps):
                capable_workers.append(worker)

        return capable_workers

    async def add_capability(self, worker_id: str, capability: str) -> bool:
        """Add a capability to a worker."""
        worker = await self.get(worker_id)
        if not worker:
            return False

        if capability not in worker.capabilities:
            worker.capabilities.append(capability)
            await self.update(worker)

        return True

    async def remove_capability(self, worker_id: str, capability: str) -> bool:
        """Remove a capability from a worker."""
        worker = await self.get(worker_id)
        if not worker:
            return False

        if capability in worker.capabilities:
            worker.capabilities.remove(capability)
            await self.update(worker)

        return True

    def _row_to_worker(self, row: Any) -> Worker:
        """Convert a database row to a Worker."""
        # Handle capabilities column - may not exist in older DBs before migration
        # Note: use row.keys() instead of 'in row' because sqlite3.Row doesn't support 'in'
        capabilities = []
        if "capabilities" in row.keys():  # noqa: SIM118
            capabilities = json.loads(row["capabilities"]) if row["capabilities"] else []

        return Worker(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            status=WorkerStatus(row["status"]),
            current_task_id=row["current_task_id"],
            capabilities=capabilities,
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


class ActionRepository:
    """Repository for Action history for undo/redo functionality.

    Records all reversible actions with their previous/new state
    to enable the Undo/Redo UX pattern from docs/07-user-experience.md.
    """

    def __init__(self, db: Database):
        self.db = db

    async def record(self, action: Action) -> Action:
        """Record a new action in the history."""
        cursor = await self.db.execute(
            """
            INSERT INTO action_history (
                action_type, entity_type, entity_id, previous_state, new_state,
                project_id, undone, undone_at, actor_type, actor_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action.action_type.value,
                action.entity_type.value,
                action.entity_id,
                json.dumps(action.previous_state) if action.previous_state else None,
                json.dumps(action.new_state) if action.new_state else None,
                str(action.project_id) if action.project_id else None,
                1 if action.undone else 0,
                action.undone_at.isoformat() if action.undone_at else None,
                action.actor_type.value,
                action.actor_id,
                action.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        action.id = cursor.lastrowid
        return action

    async def get(self, action_id: int) -> Action | None:
        """Get an action by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM action_history WHERE id = ?", (action_id,)
        )
        if not row:
            return None
        return self._row_to_action(row)

    async def get_recent(
        self,
        project_id: UUID | None = None,
        limit: int = 50,
        include_undone: bool = False,
    ) -> list[Action]:
        """Get recent actions, optionally filtered by project."""
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))

        if not include_undone:
            conditions.append("undone = 0")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT * FROM action_history
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)

        rows = await self.db.fetchall(query, tuple(params))
        return [self._row_to_action(row) for row in rows]

    async def get_last_undoable(
        self,
        project_id: UUID | None = None,
    ) -> Action | None:
        """Get the most recent action that can be undone."""
        conditions = ["undone = 0"]
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))

        query = f"""
            SELECT * FROM action_history
            WHERE {" AND ".join(conditions)}
            ORDER BY created_at DESC
            LIMIT 1
        """

        row = await self.db.fetchone(query, tuple(params))
        return self._row_to_action(row) if row else None

    async def get_last_redoable(
        self,
        project_id: UUID | None = None,
    ) -> Action | None:
        """Get the most recent undone action that can be redone."""
        conditions = ["undone = 1"]
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))

        query = f"""
            SELECT * FROM action_history
            WHERE {" AND ".join(conditions)}
            ORDER BY undone_at DESC
            LIMIT 1
        """

        row = await self.db.fetchone(query, tuple(params))
        return self._row_to_action(row) if row else None

    async def mark_undone(self, action_id: int) -> bool:
        """Mark an action as undone."""
        cursor = await self.db.execute(
            """
            UPDATE action_history
            SET undone = 1, undone_at = ?
            WHERE id = ? AND undone = 0
            """,
            (datetime.now(UTC).isoformat(), action_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def mark_redone(self, action_id: int) -> bool:
        """Mark an action as redone (undo the undo)."""
        cursor = await self.db.execute(
            """
            UPDATE action_history
            SET undone = 0, undone_at = NULL
            WHERE id = ? AND undone = 1
            """,
            (action_id,),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def clear_redo_stack(self, project_id: UUID | None = None) -> int:
        """Clear all undone actions (invalidates redo stack).

        Called when a new action is performed after an undo,
        making the redo stack invalid.
        """
        conditions = ["undone = 1"]
        params: list[Any] = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(str(project_id))

        query = f"""
            DELETE FROM action_history
            WHERE {" AND ".join(conditions)}
        """

        cursor = await self.db.execute(query, tuple(params))
        await self.db.commit()
        return cursor.rowcount

    async def get_for_entity(
        self,
        entity_type: EntityType,
        entity_id: str,
        limit: int = 50,
    ) -> list[Action]:
        """Get action history for a specific entity."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM action_history
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (entity_type.value, entity_id, limit),
        )
        return [self._row_to_action(row) for row in rows]

    async def cleanup_old(self, days: int = 7) -> int:
        """Delete actions older than the specified number of days."""
        cutoff = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Subtract days manually since timedelta is not available
        cutoff = cutoff.replace(day=cutoff.day - days)

        cursor = await self.db.execute(
            "DELETE FROM action_history WHERE created_at < ?",
            (cutoff.isoformat(),),
        )
        await self.db.commit()
        return cursor.rowcount

    def _row_to_action(self, row: Any) -> Action:
        """Convert a database row to an Action."""
        return Action(
            id=row["id"],
            action_type=ActionType(row["action_type"]),
            entity_type=EntityType(row["entity_type"]),
            entity_id=row["entity_id"],
            previous_state=json.loads(row["previous_state"]) if row["previous_state"] else None,
            new_state=json.loads(row["new_state"]) if row["new_state"] else None,
            project_id=UUID(row["project_id"]) if row["project_id"] else None,
            undone=bool(row["undone"]),
            undone_at=datetime.fromisoformat(row["undone_at"]) if row["undone_at"] else None,
            actor_type=ActorType(row["actor_type"]),
            actor_id=row["actor_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class ContextAssemblyLogRepository:
    """Repository for ContextAssemblyLog entities.

    Tracks context assembly events for enrichment pipeline observability.
    Per docs/04-context-enrichment.md "Observability" section.
    """

    def __init__(self, db: Database):
        self.db = db

    async def create(self, log: ContextAssemblyLog) -> ContextAssemblyLog:
        """Create a new context assembly log entry."""
        cursor = await self.db.execute(
            """
            INSERT INTO context_assembly_logs (
                task_id, project_id, sources_queried, candidates_found,
                items_included, tokens_used, tokens_budget, compression_applied,
                compression_ratio, stages_applied, assembly_time_ms,
                context_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log.task_id,
                str(log.project_id),
                json.dumps(log.sources_queried),
                log.candidates_found,
                log.items_included,
                log.tokens_used,
                log.tokens_budget,
                json.dumps(log.compression_applied),
                log.compression_ratio,
                json.dumps(log.stages_applied),
                log.assembly_time_ms,
                log.context_hash,
                log.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        log.id = cursor.lastrowid
        return log

    async def get(self, log_id: int) -> ContextAssemblyLog | None:
        """Get a context assembly log by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM context_assembly_logs WHERE id = ?",
            (log_id,),
        )
        if not row:
            return None
        return self._row_to_log(row)

    async def list_for_task(
        self,
        task_id: str,
        limit: int = 50,
    ) -> list[ContextAssemblyLog]:
        """List context assembly logs for a specific task."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM context_assembly_logs
            WHERE task_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (task_id, limit),
        )
        return [self._row_to_log(row) for row in rows]

    async def list_for_project(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ContextAssemblyLog]:
        """List context assembly logs for a specific project."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM context_assembly_logs
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (str(project_id), limit, offset),
        )
        return [self._row_to_log(row) for row in rows]

    async def get_stats(self, project_id: UUID) -> dict[str, Any]:
        """Get aggregated statistics for context assembly in a project.

        Returns:
            Dictionary with stats like avg_tokens, avg_assembly_time, etc.
        """
        row = await self.db.fetchone(
            """
            SELECT
                COUNT(*) as total_assemblies,
                AVG(tokens_used) as avg_tokens_used,
                AVG(tokens_budget) as avg_tokens_budget,
                AVG(assembly_time_ms) as avg_assembly_time_ms,
                AVG(items_included) as avg_items_included,
                AVG(compression_ratio) as avg_compression_ratio,
                MAX(tokens_used) as max_tokens_used,
                MIN(tokens_used) as min_tokens_used
            FROM context_assembly_logs
            WHERE project_id = ?
            """,
            (str(project_id),),
        )
        if not row:
            return {
                "total_assemblies": 0,
                "avg_tokens_used": 0,
                "avg_tokens_budget": 0,
                "avg_assembly_time_ms": 0,
                "avg_items_included": 0,
                "avg_compression_ratio": 1.0,
                "max_tokens_used": 0,
                "min_tokens_used": 0,
            }
        return {
            "total_assemblies": row["total_assemblies"] or 0,
            "avg_tokens_used": round(row["avg_tokens_used"] or 0, 1),
            "avg_tokens_budget": round(row["avg_tokens_budget"] or 0, 1),
            "avg_assembly_time_ms": round(row["avg_assembly_time_ms"] or 0, 1),
            "avg_items_included": round(row["avg_items_included"] or 0, 1),
            "avg_compression_ratio": round(row["avg_compression_ratio"] or 1.0, 3),
            "max_tokens_used": row["max_tokens_used"] or 0,
            "min_tokens_used": row["min_tokens_used"] or 0,
        }

    async def get_budget_utilization(
        self,
        project_id: UUID,
        threshold: float = 0.95,
    ) -> list[ContextAssemblyLog]:
        """Get logs where token usage exceeded threshold of budget.

        Useful for identifying when context assembly is hitting limits.
        """
        rows = await self.db.fetchall(
            """
            SELECT * FROM context_assembly_logs
            WHERE project_id = ?
              AND tokens_budget > 0
              AND CAST(tokens_used AS REAL) / tokens_budget >= ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (str(project_id), threshold),
        )
        return [self._row_to_log(row) for row in rows]

    async def cleanup_old(self, days: int = 30) -> int:
        """Delete context assembly logs older than the specified number of days."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)

        cursor = await self.db.execute(
            "DELETE FROM context_assembly_logs WHERE created_at < ?",
            (cutoff.isoformat(),),
        )
        await self.db.commit()
        return cursor.rowcount

    def _row_to_log(self, row: Any) -> ContextAssemblyLog:
        """Convert a database row to a ContextAssemblyLog."""
        return ContextAssemblyLog(
            id=row["id"],
            task_id=row["task_id"],
            project_id=UUID(row["project_id"]),
            sources_queried=json.loads(row["sources_queried"]) if row["sources_queried"] else [],
            candidates_found=row["candidates_found"] or 0,
            items_included=row["items_included"] or 0,
            tokens_used=row["tokens_used"] or 0,
            tokens_budget=row["tokens_budget"] or 0,
            compression_applied=json.loads(row["compression_applied"]) if row["compression_applied"] else [],
            compression_ratio=row["compression_ratio"] or 1.0,
            stages_applied=json.loads(row["stages_applied"]) if row["stages_applied"] else [],
            assembly_time_ms=row["assembly_time_ms"] or 0,
            context_hash=row["context_hash"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class ReasoningBankRepository:
    """Repository for TaskOutcome entities - the Reasoning Bank.

    Per docs/08-open-architecture.md "Reflexion-Based Learning" section:
    Stores and retrieves task execution outcomes to enable model routing
    optimization based on learned experience.
    """

    def __init__(self, db: Database):
        self.db = db

    async def record(self, outcome: TaskOutcome) -> TaskOutcome:
        """Record a task outcome to the reasoning bank."""
        cursor = await self.db.execute(
            """
            INSERT INTO task_outcomes (
                task_id, project_id, file_count, keywords, bead_type, has_dependencies,
                model_used, worker_type, iterations, duration_seconds,
                success, outcome, confidence, failure_reason, reflection, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.task_id,
                str(outcome.project_id),
                outcome.file_count,
                json.dumps(outcome.keywords),
                outcome.bead_type,
                outcome.has_dependencies,
                outcome.model_used,
                outcome.worker_type,
                outcome.iterations,
                outcome.duration_seconds,
                outcome.success,
                outcome.outcome,
                outcome.confidence,
                outcome.failure_reason,
                outcome.reflection,
                outcome.created_at.isoformat(),
            ),
        )
        await self.db.commit()
        outcome.id = cursor.lastrowid
        return outcome

    async def get(self, outcome_id: int) -> TaskOutcome | None:
        """Get a task outcome by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM task_outcomes WHERE id = ?",
            (outcome_id,),
        )
        if not row:
            return None
        return self._row_to_outcome(row)

    async def get_for_task(self, task_id: str) -> TaskOutcome | None:
        """Get the outcome for a specific task."""
        row = await self.db.fetchone(
            "SELECT * FROM task_outcomes WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        if not row:
            return None
        return self._row_to_outcome(row)

    async def list_for_project(
        self,
        project_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskOutcome]:
        """List task outcomes for a project."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM task_outcomes
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (str(project_id), limit, offset),
        )
        return [self._row_to_outcome(row) for row in rows]

    async def find_similar(
        self,
        keywords: list[str],
        bead_type: str,
        file_count: int | None = None,
        min_similarity: float = 0.3,
        limit: int = 20,
        project_id: UUID | None = None,
    ) -> list[tuple[TaskOutcome, float]]:
        """Find similar past task outcomes using keyword-based similarity.

        Uses Jaccard similarity between keyword sets to find related tasks.
        Returns list of (outcome, similarity_score) tuples sorted by similarity.

        Args:
            keywords: Keywords from the current task
            bead_type: Type of bead (task, subtask, epic)
            file_count: Optional file count to factor in similarity
            min_similarity: Minimum similarity threshold (0.0-1.0)
            limit: Maximum results to return
            project_id: Optional project scope for similarity search

        Returns:
            List of (TaskOutcome, similarity_score) tuples
        """
        # Query outcomes with same bead type
        query = """
            SELECT * FROM task_outcomes
            WHERE bead_type = ?
        """
        params: list[Any] = [bead_type]

        if project_id:
            query += " AND project_id = ?"
            params.append(str(project_id))

        query += " ORDER BY created_at DESC LIMIT 200"  # Sample recent outcomes

        rows = await self.db.fetchall(query, tuple(params))

        # Calculate similarity for each outcome
        keyword_set = {k.lower() for k in keywords}
        results: list[tuple[TaskOutcome, float]] = []

        for row in rows:
            outcome = self._row_to_outcome(row)
            outcome_keywords = {k.lower() for k in outcome.keywords}

            # Jaccard similarity
            if keyword_set or outcome_keywords:
                intersection = len(keyword_set & outcome_keywords)
                union = len(keyword_set | outcome_keywords)
                keyword_similarity = intersection / union if union > 0 else 0.0
            else:
                keyword_similarity = 0.0

            # File count similarity (if provided)
            file_similarity = 1.0
            if file_count is not None and outcome.file_count > 0:
                # Use ratio of smaller to larger
                min_count = min(file_count, outcome.file_count)
                max_count = max(file_count, outcome.file_count)
                file_similarity = min_count / max_count if max_count > 0 else 1.0

            # Combined similarity (keywords weighted higher)
            similarity = keyword_similarity * 0.7 + file_similarity * 0.3

            if similarity >= min_similarity:
                results.append((outcome, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    async def get_model_success_rates(
        self,
        bead_type: str | None = None,
        project_id: UUID | None = None,
        min_samples: int = 3,
    ) -> dict[str, dict[str, Any]]:
        """Get success rates per model.

        Returns:
            Dictionary mapping model_used to stats:
            {
                "claude-sonnet": {
                    "total": 50,
                    "success": 45,
                    "success_rate": 0.9,
                    "avg_iterations": 2.3,
                    "avg_duration_seconds": 120
                }
            }
        """
        query = """
            SELECT
                model_used,
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(iterations) as avg_iterations,
                AVG(duration_seconds) as avg_duration
            FROM task_outcomes
            WHERE 1=1
        """
        params: list[Any] = []

        if bead_type:
            query += " AND bead_type = ?"
            params.append(bead_type)

        if project_id:
            query += " AND project_id = ?"
            params.append(str(project_id))

        query += " GROUP BY model_used HAVING COUNT(*) >= ?"
        params.append(min_samples)

        rows = await self.db.fetchall(query, tuple(params))

        result = {}
        for row in rows:
            model = row["model_used"]
            total = row["total"]
            success = row["success_count"]
            result[model] = {
                "total": total,
                "success": success,
                "success_rate": success / total if total > 0 else 0.0,
                "avg_iterations": round(row["avg_iterations"] or 0, 2),
                "avg_duration_seconds": round(row["avg_duration"] or 0, 1),
            }

        return result

    async def get_stats(self, project_id: UUID | None = None) -> dict[str, Any]:
        """Get aggregated statistics for the reasoning bank.

        Returns:
            Dictionary with stats like total_outcomes, success_rate, etc.
        """
        query = """
            SELECT
                COUNT(*) as total_outcomes,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
                AVG(iterations) as avg_iterations,
                AVG(duration_seconds) as avg_duration,
                AVG(confidence) as avg_confidence
            FROM task_outcomes
        """
        params: list[Any] = []

        if project_id:
            query += " WHERE project_id = ?"
            params.append(str(project_id))

        row = await self.db.fetchone(query, tuple(params) if params else ())

        if not row or row["total_outcomes"] == 0:
            return {
                "total_outcomes": 0,
                "success_count": 0,
                "success_rate": 0.0,
                "avg_iterations": 0.0,
                "avg_duration_seconds": 0.0,
                "avg_confidence": 0.0,
            }

        total = row["total_outcomes"]
        success = row["success_count"] or 0
        return {
            "total_outcomes": total,
            "success_count": success,
            "success_rate": success / total if total > 0 else 0.0,
            "avg_iterations": round(row["avg_iterations"] or 0, 2),
            "avg_duration_seconds": round(row["avg_duration"] or 0, 1),
            "avg_confidence": round(row["avg_confidence"] or 0, 3),
        }

    async def cleanup_old(self, days: int = 90) -> int:
        """Delete task outcomes older than the specified number of days."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)

        cursor = await self.db.execute(
            "DELETE FROM task_outcomes WHERE created_at < ?",
            (cutoff.isoformat(),),
        )
        await self.db.commit()
        return cursor.rowcount

    def _row_to_outcome(self, row: Any) -> TaskOutcome:
        """Convert a database row to a TaskOutcome."""
        return TaskOutcome(
            id=row["id"],
            task_id=row["task_id"],
            project_id=UUID(row["project_id"]),
            file_count=row["file_count"] or 0,
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            bead_type=row["bead_type"],
            has_dependencies=bool(row["has_dependencies"]),
            model_used=row["model_used"],
            worker_type=row["worker_type"],
            iterations=row["iterations"] or 1,
            duration_seconds=row["duration_seconds"] or 0,
            success=bool(row["success"]),
            outcome=row["outcome"],
            confidence=row["confidence"] or 1.0,
            failure_reason=row["failure_reason"],
            reflection=row["reflection"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
