"""Individual enrichment stages."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ringmaster.domain import Project, Task

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from an enrichment stage."""

    content: str
    tokens_estimate: int = 0
    sources: list[str] | None = None


class BaseStage(ABC):
    """Base class for enrichment stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name."""
        ...

    @abstractmethod
    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Process this stage and return content.

        Returns None if the stage has nothing to contribute.
        """
        ...


class TaskContextStage(BaseStage):
    """Stage 1: Task context."""

    @property
    def name(self) -> str:
        return "task_context"

    async def process(self, task: Task, project: Project) -> StageResult:
        """Build task context."""
        parts = [
            f"# Task: {task.title}",
            f"ID: {task.id}",
            f"Priority: {task.priority.value}",
            f"Attempt: {task.attempts + 1}/{task.max_attempts}",
        ]

        if task.description:
            parts.extend(["", "## Description", task.description])

        content = "\n".join(parts)
        return StageResult(
            content=content,
            tokens_estimate=len(content) // 4,
            sources=["task"],
        )


class ProjectContextStage(BaseStage):
    """Stage 2: Project context."""

    @property
    def name(self) -> str:
        return "project_context"

    async def process(self, task: Task, project: Project) -> StageResult:
        """Build project context."""
        parts = [
            "## Project Context",
            f"Name: {project.name}",
        ]

        if project.description:
            parts.append(f"Description: {project.description}")
        if project.repo_url:
            parts.append(f"Repository: {project.repo_url}")
        if project.tech_stack:
            parts.append(f"Tech Stack: {', '.join(project.tech_stack)}")

        content = "\n".join(parts)
        return StageResult(
            content=content,
            tokens_estimate=len(content) // 4,
            sources=["project"],
        )


class CodeContextStage(BaseStage):
    """Stage 3: Code context (relevant files)."""

    @property
    def name(self) -> str:
        return "code_context"

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build code context.

        TODO: Implement intelligent file selection:
        - Parse task description for file references
        - Use embeddings or keyword matching
        - Include imports and dependencies
        """
        # Placeholder - skip for now
        return None


class HistoryContextStage(BaseStage):
    """Stage 4: Conversation history with RLM summarization."""

    @property
    def name(self) -> str:
        return "history_context"

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build history context with RLM compression.

        TODO: Implement RLM summarization:
        - Fetch chat history from database
        - Apply hierarchical summarization
        - Include key decisions
        """
        # Placeholder - skip for now
        return None


class RefinementStage(BaseStage):
    """Stage 5: Refinement and safety guardrails."""

    @property
    def name(self) -> str:
        return "refinement"

    async def process(self, task: Task, project: Project) -> StageResult:
        """Build refinement context."""
        parts = [
            "## Instructions",
            "",
            "1. Implement the changes described above",
            "2. Ensure all tests pass",
            "3. Follow project coding conventions",
            "4. Add tests for new functionality",
            "",
            "## Completion Signal",
            "",
            "When complete, output: <promise>COMPLETE</promise>",
        ]

        content = "\n".join(parts)
        return StageResult(
            content=content,
            tokens_estimate=len(content) // 4,
        )
