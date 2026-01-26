"""Bead Creator service for transforming user input into tasks.

This is the main entry point that orchestrates:
1. Parsing user input
2. Finding existing matches
3. Decomposing large tasks
4. Creating tasks in the database
"""

from dataclasses import dataclass, field
from uuid import UUID

from ringmaster.creator.decomposer import decompose_candidate
from ringmaster.creator.matcher import find_matching_task, find_related_tasks
from ringmaster.creator.parser import ParsedInput, TaskCandidate, parse_user_input
from ringmaster.db import Database, TaskRepository
from ringmaster.domain import (
    Dependency,
    Epic,
    Priority,
    Subtask,
    Task,
    TaskStatus,
)
from ringmaster.events import EventType, event_bus


@dataclass
class CreatedTask:
    """Information about a created task."""

    task: Task | Epic | Subtask
    was_updated: bool = False  # True if matched existing and updated
    matched_task_id: str | None = None  # ID of task that was matched


@dataclass
class CreationResult:
    """Result of creating tasks from user input."""

    parsed: ParsedInput
    created_tasks: list[CreatedTask] = field(default_factory=list)
    epic: Epic | None = None  # If an epic was created
    dependencies_created: list[Dependency] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)  # Status/info messages


class BeadCreator:
    """Service for creating tasks from natural language input."""

    def __init__(
        self,
        db: Database,
        match_threshold: float = 0.6,
        auto_decompose: bool = True,
    ):
        self.db = db
        self.repo = TaskRepository(db)
        self.match_threshold = match_threshold
        self.auto_decompose = auto_decompose

    async def create_from_input(
        self,
        project_id: UUID,
        text: str,
        priority: Priority = Priority.P2,
    ) -> CreationResult:
        """Create tasks from user input text.

        This is the main entry point. It:
        1. Parses the input to extract task candidates
        2. For each candidate, checks for existing matches
        3. Creates new tasks or updates existing ones
        4. Handles epic creation and decomposition
        5. Sets up dependencies based on ordering
        """
        result = CreationResult(parsed=parse_user_input(text))

        if not result.parsed.candidates:
            result.messages.append("No actionable items found in input")
            return result

        # Get existing tasks for matching
        existing_tasks = await self.repo.list_tasks(project_id=project_id)

        # If this should be an epic, create the epic first
        if result.parsed.is_epic:
            epic = Epic(
                project_id=project_id,
                title=result.parsed.suggested_epic_title,
                description=text,
                priority=priority,
                status=TaskStatus.READY,
            )
            created_epic = await self.repo.create_task(epic)
            result.epic = created_epic
            result.messages.append(f"Created epic: {created_epic.id}")

            await event_bus.emit(
                EventType.TASK_CREATED,
                data={"task_id": created_epic.id, "title": created_epic.title, "type": "epic"},
                project_id=str(project_id),
            )

        # Process each candidate
        previous_task_id: str | None = None

        for candidate in result.parsed.candidates:
            created_task = await self._process_candidate(
                project_id=project_id,
                candidate=candidate,
                existing_tasks=existing_tasks,
                priority=priority,
                parent_id=result.epic.id if result.epic else None,
            )

            if created_task:
                result.created_tasks.append(created_task)

                # Create dependency on previous task if ordering suggests it
                if previous_task_id and candidate.order_hint > 0:
                    dep = await self._create_dependency(
                        child_id=created_task.task.id,
                        parent_id=previous_task_id,
                    )
                    if dep:
                        result.dependencies_created.append(dep)

                previous_task_id = created_task.task.id

        # Update epic with child IDs
        if result.epic and result.created_tasks:
            result.epic.child_ids = [ct.task.id for ct in result.created_tasks]
            await self.repo.update_task(result.epic)

        result.messages.append(f"Created {len(result.created_tasks)} task(s)")
        return result

    async def _process_candidate(
        self,
        project_id: UUID,
        candidate: TaskCandidate,
        existing_tasks: list[Task | Epic | Subtask],
        priority: Priority,
        parent_id: str | None = None,
    ) -> CreatedTask | None:
        """Process a single task candidate.

        Checks for matches, decomposes if needed, and creates the task.
        """
        # Check for existing match
        matched, score = find_matching_task(
            candidate.raw_text,
            existing_tasks,
            threshold=self.match_threshold,
        )

        if matched:
            # Update existing task with new context
            if candidate.raw_text not in (matched.description or ""):
                matched.description = (matched.description or "") + f"\n\nUpdated: {candidate.raw_text}"
                await self.repo.update_task(matched)

                await event_bus.emit(
                    EventType.TASK_UPDATED,
                    data={"task_id": matched.id, "reason": "matched_input"},
                    project_id=str(project_id),
                )

            return CreatedTask(
                task=matched,
                was_updated=True,
                matched_task_id=matched.id,
            )

        # Check if decomposition is needed
        if self.auto_decompose:
            decomp = decompose_candidate(candidate)
            if decomp.should_decompose and decomp.subtasks:
                # Create parent task for the decomposed work
                parent_task = Task(
                    project_id=project_id,
                    title=candidate.to_title(),
                    description=candidate.raw_text,
                    priority=priority,
                    status=TaskStatus.READY,
                    parent_id=parent_id,
                )
                created_parent = await self.repo.create_task(parent_task)

                await event_bus.emit(
                    EventType.TASK_CREATED,
                    data={"task_id": created_parent.id, "title": created_parent.title, "type": "task"},
                    project_id=str(project_id),
                )

                # Create subtasks
                subtask_ids: list[str] = []
                for subtask_candidate in decomp.subtasks:
                    subtask = Subtask(
                        project_id=project_id,
                        title=subtask_candidate.to_title(),
                        description=subtask_candidate.raw_text,
                        priority=priority,
                        parent_id=created_parent.id,
                        status=TaskStatus.READY,
                    )
                    created_subtask = await self.repo.create_task(subtask)
                    subtask_ids.append(created_subtask.id)

                    await event_bus.emit(
                        EventType.TASK_CREATED,
                        data={"task_id": created_subtask.id, "title": created_subtask.title, "type": "subtask"},
                        project_id=str(project_id),
                    )

                # Update parent with subtask IDs
                created_parent.subtask_ids = subtask_ids
                await self.repo.update_task(created_parent)

                return CreatedTask(task=created_parent)

        # Create a regular task
        task = Task(
            project_id=project_id,
            title=candidate.to_title(),
            description=candidate.raw_text,
            priority=priority,
            status=TaskStatus.READY,
            parent_id=parent_id,
        )
        created = await self.repo.create_task(task)

        await event_bus.emit(
            EventType.TASK_CREATED,
            data={"task_id": created.id, "title": created.title, "type": "task"},
            project_id=str(project_id),
        )

        return CreatedTask(task=created)

    async def _create_dependency(
        self,
        child_id: str,
        parent_id: str,
    ) -> Dependency | None:
        """Create a dependency between tasks."""
        try:
            dep = Dependency(child_id=child_id, parent_id=parent_id)
            return await self.repo.add_dependency(dep)
        except Exception:
            # Ignore dependency creation errors (e.g., circular dependencies)
            return None

    async def suggest_related(
        self,
        project_id: UUID,
        text: str,
        max_results: int = 5,
    ) -> list[tuple[Task | Epic | Subtask, float]]:
        """Find existing tasks related to the input text.

        Useful for suggesting context or potential duplicates before creating.
        """
        existing = await self.repo.list_tasks(project_id=project_id)
        return find_related_tasks(text, existing, max_results=max_results)
