"""Enrichment pipeline for assembling prompts with context.

Based on docs/04-context-enrichment.md:
- 5-layer recursive summarization
- RLM-based chat history compression
- Project and code context assembly
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ringmaster.domain import Project, Task

logger = logging.getLogger(__name__)


@dataclass
class PromptMetrics:
    """Metrics about the assembled prompt."""

    estimated_tokens: int = 0
    context_sources: list[str] = field(default_factory=list)
    stages_applied: list[str] = field(default_factory=list)


@dataclass
class AssembledPrompt:
    """Result of the enrichment pipeline."""

    system_prompt: str
    user_prompt: str
    context_hash: str
    metrics: PromptMetrics


class EnrichmentPipeline:
    """Pipeline for enriching task prompts with context.

    The pipeline assembles context in layers:
    1. Task Context - Task title, description, state, iteration
    2. Project Context - Repo URL, tech stack, conventions
    3. Code Context - Relevant files, imports, dependencies
    4. History Context - RLM-summarized conversation history
    5. Refinement Context - Safety guardrails, constraints
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        max_context_tokens: int = 100000,
    ):
        self.project_dir = project_dir or Path.cwd()
        self.max_context_tokens = max_context_tokens

    async def enrich(self, task: Task, project: Project) -> AssembledPrompt:
        """Assemble an enriched prompt for a task.

        Args:
            task: The task to create a prompt for.
            project: The project the task belongs to.

        Returns:
            AssembledPrompt with full context.
        """
        metrics = PromptMetrics()
        context_parts: list[str] = []

        # Layer 1: Task Context
        task_context = self._build_task_context(task)
        context_parts.append(task_context)
        metrics.stages_applied.append("task_context")

        # Layer 2: Project Context
        project_context = self._build_project_context(project)
        context_parts.append(project_context)
        metrics.stages_applied.append("project_context")

        # Layer 3: Code Context (simplified for now)
        # TODO: Implement intelligent file selection based on task
        code_context = await self._build_code_context(task, project)
        if code_context:
            context_parts.append(code_context)
            metrics.stages_applied.append("code_context")

        # Layer 4: History Context (placeholder)
        # TODO: Implement RLM summarization
        history_context = await self._build_history_context(task, project)
        if history_context:
            context_parts.append(history_context)
            metrics.stages_applied.append("history_context")

        # Layer 5: Refinement Context
        refinement_context = self._build_refinement_context(task)
        context_parts.append(refinement_context)
        metrics.stages_applied.append("refinement_context")

        # Assemble prompts
        system_prompt = self._build_system_prompt(project)
        user_prompt = "\n\n".join(context_parts)

        # Calculate context hash for deduplication
        context_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:16]

        # Estimate tokens (rough: ~4 chars per token)
        metrics.estimated_tokens = len(user_prompt) // 4

        return AssembledPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context_hash=context_hash,
            metrics=metrics,
        )

    def _build_system_prompt(self, project: Project) -> str:
        """Build the system prompt."""
        parts = [
            "You are an expert software engineer working on a coding task.",
            f"Project: {project.name}",
        ]

        if project.tech_stack:
            parts.append(f"Tech Stack: {', '.join(project.tech_stack)}")

        parts.extend([
            "",
            "Guidelines:",
            "- Write clean, maintainable code",
            "- Follow the project's existing patterns and conventions",
            "- Include appropriate error handling",
            "- Write tests for new functionality",
            "- Commit changes with descriptive messages",
        ])

        return "\n".join(parts)

    def _build_task_context(self, task: Task) -> str:
        """Build task context layer."""
        parts = [
            f"# Task: {task.title}",
            f"ID: {task.id}",
            f"Priority: {task.priority.value}",
            f"Status: {task.status.value}",
            f"Attempt: {task.attempts + 1} of {task.max_attempts}",
        ]

        if task.description:
            parts.extend(["", "## Description", task.description])

        return "\n".join(parts)

    def _build_project_context(self, project: Project) -> str:
        """Build project context layer."""
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

        return "\n".join(parts)

    async def _build_code_context(self, task: Task, project: Project) -> str | None:
        """Build code context layer.

        TODO: Implement intelligent file selection:
        - Parse task description for file references
        - Find related files using embeddings or keyword matching
        - Include dependency information
        """
        # Placeholder - return None for now
        # Real implementation would:
        # 1. Search for relevant files based on task description
        # 2. Include imports and dependencies
        # 3. Apply RLM compression for large files
        return None

    async def _build_history_context(self, task: Task, project: Project) -> str | None:
        """Build history context layer with RLM summarization.

        TODO: Implement RLM (Recursive Language Model) summarization:
        - Fetch recent chat history for this task
        - Summarize using hierarchical compression
        - Include key decisions and context
        """
        # Placeholder - return None for now
        return None

    def _build_refinement_context(self, task: Task) -> str:
        """Build refinement context with safety guardrails."""
        parts = [
            "## Instructions",
            "",
            "1. Implement the changes described above",
            "2. Ensure all existing tests continue to pass",
            "3. Add tests for any new functionality",
            "4. Follow the project's coding style",
            "",
            "## Completion",
            "",
            "When you have successfully completed the task:",
            "- Ensure all tests pass",
            "- Commit your changes with a descriptive message",
            "- Output the completion signal: <promise>COMPLETE</promise>",
            "",
            "If you encounter blockers or need clarification:",
            "- Document what you tried",
            "- Explain the issue clearly",
            "- Do NOT output the completion signal",
        ]

        return "\n".join(parts)


# Singleton for convenience
_pipeline: EnrichmentPipeline | None = None


def get_pipeline(project_dir: Path | None = None) -> EnrichmentPipeline:
    """Get or create the enrichment pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = EnrichmentPipeline(project_dir=project_dir)
    return _pipeline
