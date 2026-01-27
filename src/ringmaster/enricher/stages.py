"""Individual enrichment stages."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ringmaster.domain import Project, Task

if TYPE_CHECKING:
    from ringmaster.db import Database
    from ringmaster.enricher.rlm import RLMSummarizer
from ringmaster.enricher.code_context import (
    CodeContextExtractor,
    format_code_context,
)
from ringmaster.enricher.deployment_context import (
    DeploymentContextExtractor,
    format_deployment_context,
)

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

    def __init__(self, project_dir: Path | None = None):
        self._project_dir = project_dir

    @property
    def name(self) -> str:
        return "code_context"

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build code context using intelligent file selection.

        Extracts relevant code files based on:
        - Explicit file references in task description
        - Keyword matching for function/class names
        - Import dependencies
        """
        if not task.description:
            return None

        project_dir = self._project_dir or Path.cwd()
        extractor = CodeContextExtractor(
            project_dir=project_dir,
            max_tokens=12000,
            max_files=10,
            max_file_lines=500,
        )

        result = extractor.extract(task.description)

        if not result.files:
            return None

        content = format_code_context(result, project_dir)
        sources = [str(f.path) for f in result.files]

        return StageResult(
            content=content,
            tokens_estimate=result.total_tokens,
            sources=sources,
        )


class DeploymentContextStage(BaseStage):
    """Stage 4: Deployment and infrastructure context."""

    def __init__(self, project_dir: Path | None = None):
        self._project_dir = project_dir

    @property
    def name(self) -> str:
        return "deployment_context"

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build deployment context for infrastructure tasks.

        Extracts:
        - Environment configs (.env files with secret redaction)
        - Docker Compose configurations
        - Kubernetes manifests
        - Helm values
        - CI/CD workflow definitions and status
        """
        if not task.description:
            return None

        project_dir = self._project_dir or Path.cwd()
        extractor = DeploymentContextExtractor(
            project_dir=project_dir,
            max_tokens=3000,
            max_files=8,
            redact_secrets=True,
            include_cicd_status=True,
        )

        result = extractor.extract(task.description)

        if not result.files and not result.cicd_runs:
            return None

        content = format_deployment_context(result, project_dir)
        sources = [str(f.path) for f in result.files]

        return StageResult(
            content=content,
            tokens_estimate=result.total_tokens,
            sources=sources,
        )


class HistoryContextStage(BaseStage):
    """Stage 5: Conversation history with RLM summarization."""

    def __init__(self, db: Database | None = None):
        """Initialize with optional database connection.

        Args:
            db: Database connection for chat history access.
                If None, this stage will be skipped.
        """
        self._db = db
        self._rlm_summarizer: RLMSummarizer | None = None

    @property
    def name(self) -> str:
        return "history_context"

    @property
    def rlm_summarizer(self) -> RLMSummarizer | None:
        """Lazy initialization of RLM summarizer."""
        if self._rlm_summarizer is None and self._db is not None:
            from ringmaster.enricher.rlm import RLMSummarizer

            self._rlm_summarizer = RLMSummarizer(self._db)
        return self._rlm_summarizer

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build history context with RLM compression.

        Fetches chat history from database, applies hierarchical
        summarization to older messages, and preserves key decisions
        for context continuity.

        Note: Uses project-level chat history (task_id=None) since
        conversations are typically at the project level, not task level.
        """
        if self.rlm_summarizer is None:
            # No database configured, skip this stage
            return None

        try:
            # Get compressed history context for the project
            # We use task_id=None to get all project-level conversation history,
            # which provides the most relevant context for workers
            context = await self.rlm_summarizer.get_history_context(
                project_id=project.id,
                task_id=None,
            )

            # If no messages, skip this stage
            if context.total_messages == 0:
                return None

            # Format for prompt inclusion
            content = self.rlm_summarizer.format_for_prompt(context)
            sources = [f"chat:{context.total_messages} messages"]

            return StageResult(
                content=content,
                tokens_estimate=context.estimated_tokens,
                sources=sources,
            )

        except Exception as e:
            logger.warning("Failed to build history context: %s", e)
            return None


class RefinementStage(BaseStage):
    """Stage 6: Refinement and safety guardrails."""

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
