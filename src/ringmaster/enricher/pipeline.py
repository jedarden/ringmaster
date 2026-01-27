"""Enrichment pipeline for assembling prompts with context.

Based on docs/04-context-enrichment.md:
- 5-layer recursive summarization
- RLM-based chat history compression
- Project and code context assembly
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ringmaster.db import Database
from ringmaster.domain import Project, Task
from ringmaster.enricher.code_context import (
    CodeContextExtractor,
    format_code_context,
)
from ringmaster.enricher.deployment_context import (
    DeploymentContextExtractor,
    format_deployment_context,
)
from ringmaster.enricher.rlm import CompressionConfig, RLMSummarizer

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
    4. Deployment Context - Env configs, K8s manifests, CI/CD status
    5. History Context - RLM-summarized conversation history
    6. Logs Context - Error logs and stack traces for debugging
    7. Research Context - Prior agent outputs and related task summaries
    8. Refinement Context - Safety guardrails, constraints
    """

    def __init__(
        self,
        project_dir: Path | None = None,
        max_context_tokens: int = 100000,
        db: Database | None = None,
        rlm_config: CompressionConfig | None = None,
    ):
        self.project_dir = project_dir or Path.cwd()
        self.max_context_tokens = max_context_tokens
        self.db = db
        self.rlm_config = rlm_config or CompressionConfig()
        self._rlm_summarizer: RLMSummarizer | None = None

    @property
    def rlm_summarizer(self) -> RLMSummarizer | None:
        """Get or create the RLM summarizer (lazy initialization)."""
        if self._rlm_summarizer is None and self.db is not None:
            self._rlm_summarizer = RLMSummarizer(self.db, self.rlm_config)
        return self._rlm_summarizer

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

        # Layer 4: Deployment Context (for infra-related tasks)
        deployment_context = await self._build_deployment_context(task, project)
        if deployment_context:
            context_parts.append(deployment_context)
            metrics.stages_applied.append("deployment_context")

        # Layer 5: History Context (RLM-summarized conversation history)
        history_context = await self._build_history_context(task, project)
        if history_context:
            context_parts.append(history_context)
            metrics.stages_applied.append("history_context")

        # Layer 6: Logs Context (for debugging tasks)
        logs_context = await self._build_logs_context(task, project)
        if logs_context:
            context_parts.append(logs_context)
            metrics.stages_applied.append("logs_context")

        # Layer 7: Research Context (prior agent outputs)
        research_context = await self._build_research_context(task, project)
        if research_context:
            context_parts.append(research_context)
            metrics.stages_applied.append("research_context")

        # Layer 8: Refinement Context
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

        Extracts relevant code files based on:
        - Explicit file references in task description
        - Keyword matching for function/class names
        - Import dependencies
        """
        if not task.description:
            return None

        extractor = CodeContextExtractor(
            project_dir=self.project_dir,
            max_tokens=12000,
            max_files=10,
            max_file_lines=500,
        )

        result = extractor.extract(task.description)

        if not result.files:
            logger.debug("No relevant code files found for task %s", task.id)
            return None

        logger.info(
            "Found %d relevant files (~%d tokens) for task %s",
            len(result.files),
            result.total_tokens,
            task.id,
        )

        return format_code_context(result, self.project_dir)

    async def _build_deployment_context(self, task: Task, project: Project) -> str | None:
        """Build deployment context layer for infrastructure tasks.

        Extracts relevant deployment files based on:
        - Environment configs (.env files with secret redaction)
        - Docker Compose configurations
        - Kubernetes manifests
        - Helm values
        - CI/CD workflow definitions and status
        """
        if not task.description:
            return None

        extractor = DeploymentContextExtractor(
            project_dir=self.project_dir,
            max_tokens=3000,
            max_files=8,
            redact_secrets=True,
            include_cicd_status=True,
        )

        result = extractor.extract(task.description)

        if not result.files and not result.cicd_runs:
            logger.debug("No relevant deployment files found for task %s", task.id)
            return None

        logger.info(
            "Found %d deployment files and %d CI/CD runs for task %s",
            len(result.files),
            len(result.cicd_runs),
            task.id,
        )

        return format_deployment_context(result, self.project_dir)

    async def _build_history_context(self, task: Task, project: Project) -> str | None:
        """Build history context layer with RLM summarization.

        Uses the RLM summarizer to:
        - Fetch recent chat history for this task
        - Summarize older messages using hierarchical compression
        - Include key decisions and context
        """
        if self.rlm_summarizer is None:
            logger.debug("No database configured, skipping history context")
            return None

        try:
            # Get compressed history context
            context = await self.rlm_summarizer.get_history_context(
                project_id=project.id,
                task_id=task.id,
            )

            # If no messages, skip this layer
            if context.total_messages == 0:
                logger.debug("No chat history found for task %s", task.id)
                return None

            # Format for prompt inclusion
            formatted = self.rlm_summarizer.format_for_prompt(context)
            logger.info(
                "Built history context: %d messages, ~%d tokens",
                context.total_messages,
                context.estimated_tokens,
            )
            return formatted

        except Exception as e:
            logger.warning("Failed to build history context: %s", e)
            return None

    async def _build_logs_context(self, task: Task, project: Project) -> str | None:
        """Build logs context layer for debugging tasks.

        Per docs/04-context-enrichment.md section 6, this stage provides:
        - Error logs from the last 24 hours
        - Service logs filtered by relevance
        - Stack traces when debugging crashes

        Only fetches logs when the task appears to be debugging-related.
        """
        if self.db is None:
            logger.debug("No database configured, skipping logs context")
            return None

        # Check if task is debugging-related
        debug_keywords = {
            "error", "bug", "fix", "debug", "crash", "fail", "failing",
            "broken", "issue", "problem", "exception", "traceback",
            "stack trace", "500", "404", "timeout", "investigate", "diagnose",
        }

        text = f"{task.title} {task.description or ''}".lower()
        if not any(keyword in text for keyword in debug_keywords):
            logger.debug("Task %s doesn't appear debugging-related", task.id)
            return None

        try:
            from datetime import timedelta

            cutoff = datetime.now(UTC) - timedelta(hours=24)
            cutoff_str = cutoff.isoformat()

            # First, try to get task-specific logs
            task_logs = await self.db.fetchall(
                """
                SELECT * FROM logs
                WHERE task_id = ?
                ORDER BY timestamp DESC
                LIMIT 50
                """,
                (task.id,),
            )

            # Also get project-level error logs
            project_logs = await self.db.fetchall(
                """
                SELECT * FROM logs
                WHERE project_id = ? AND level IN ('error', 'critical') AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 30
                """,
                (str(project.id), cutoff_str),
            )

            # Combine and dedupe
            seen_ids = set()
            logs = []
            for row in list(task_logs) + list(project_logs):
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    logs.append(row)

            if not logs:
                logger.debug("No relevant logs found for task %s", task.id)
                return None

            # Format logs for context
            formatted = self._format_logs_for_context(logs)

            logger.info(
                "Built logs context: %d entries for task %s",
                len(logs),
                task.id,
            )

            return formatted

        except Exception as e:
            logger.warning("Failed to build logs context: %s", e)
            return None

    def _format_logs_for_context(self, logs: list) -> str:
        """Format log entries for prompt inclusion."""
        import json

        parts = ["## Relevant Logs", ""]

        for log in logs[:50]:  # Limit to 50 entries
            timestamp = log["timestamp"]
            level = log["level"].upper()
            component = log["component"]
            message = log["message"]

            # Format the log entry
            entry = f"[{timestamp}] {level} ({component}): {message}"

            # Include extra data if present and relevant
            if log["data"]:
                try:
                    data = json.loads(log["data"])
                    # Check for stack traces or error details
                    if "traceback" in data or "stack_trace" in data:
                        trace = data.get("traceback") or data.get("stack_trace")
                        entry += f"\n  Traceback: {trace[:500]}"
                    elif "error" in data or "exception" in data:
                        error_detail = data.get("error") or data.get("exception")
                        entry += f"\n  Error: {error_detail}"
                except (json.JSONDecodeError, TypeError):
                    pass

            parts.append(entry)

        return "\n".join(parts)

    async def _build_research_context(self, task: Task, project: Project) -> str | None:
        """Build research context from prior task outputs.

        Per docs/04-context-enrichment.md section 2, this stage provides:
        - Prior agent task outputs (when task is related)
        - Task completion summaries
        - Related exploration/spike results
        """
        if self.db is None:
            logger.debug("No database configured, skipping research context")
            return None

        try:
            # Import the ResearchContextStage for keyword extraction logic
            from ringmaster.enricher.stages import ResearchContextStage

            stage = ResearchContextStage(
                db=self.db,
                max_tokens=4000,
                max_results=5,
                min_relevance_score=0.3,
            )

            result = await stage.process(task, project)

            if result is None:
                logger.debug("No related research found for task %s", task.id)
                return None

            logger.info(
                "Built research context: ~%d tokens for task %s",
                result.tokens_estimate,
                task.id,
            )

            return result.content

        except Exception as e:
            logger.warning("Failed to build research context: %s", e)
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


def get_pipeline(
    project_dir: Path | None = None,
    db: Database | None = None,
) -> EnrichmentPipeline:
    """Get or create the enrichment pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = EnrichmentPipeline(project_dir=project_dir, db=db)
    elif db is not None and _pipeline.db is None:
        # Update with database if provided later
        _pipeline.db = db
        _pipeline._rlm_summarizer = None  # Reset to pick up new db
    return _pipeline
