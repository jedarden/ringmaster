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
from ringmaster.enricher.documentation_context import (
    DocumentationContextExtractor,
    format_documentation_context,
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


class DocumentationContextStage(BaseStage):
    """Stage 5: Documentation context (README, ADRs, conventions).

    Per docs/04-context-enrichment.md section 3, this stage provides:
    - Project README and goals
    - Architecture Decision Records (ADRs)
    - Coding conventions and style guides
    - API specifications (when API-related)

    Always includes README and conventions. ADRs and API specs
    are filtered by relevance to the task.
    """

    def __init__(self, project_dir: Path | None = None):
        self._project_dir = project_dir

    @property
    def name(self) -> str:
        return "documentation_context"

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build documentation context.

        Extracts relevant documentation files based on:
        - README (always included)
        - Coding conventions (always included)
        - ADRs (filtered by relevance to task)
        - API specs (when task is API-related)
        """
        if not task.description:
            return None

        project_dir = self._project_dir or Path.cwd()
        extractor = DocumentationContextExtractor(
            project_dir=project_dir,
            max_tokens=3000,
            max_files=8,
            max_file_lines=500,
            include_adrs=True,
            include_api_specs=True,
        )

        result = extractor.extract(task.description)

        if not result.files:
            return None

        content = format_documentation_context(result, project_dir)
        sources = [str(f.path) for f in result.files]

        return StageResult(
            content=content,
            tokens_estimate=result.total_tokens,
            sources=sources,
        )


class HistoryContextStage(BaseStage):
    """Stage 6: Conversation history with RLM summarization."""

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


class LogsContextStage(BaseStage):
    """Stage 7: Logs context for debugging tasks.

    Per docs/04-context-enrichment.md section 6, this stage provides:
    - Error logs from the last 24 hours
    - Service logs filtered by relevance
    - Stack traces when debugging crashes
    """

    # Keywords that indicate a task is debugging-related
    DEBUG_KEYWORDS = {
        "error",
        "bug",
        "fix",
        "debug",
        "crash",
        "fail",
        "failing",
        "broken",
        "issue",
        "problem",
        "exception",
        "traceback",
        "stack trace",
        "500",
        "404",
        "timeout",
        "hang",
        "slow",
        "performance",
        "investigate",
        "diagnose",
    }

    def __init__(
        self,
        db: Database | None = None,
        max_tokens: int = 3000,
        log_window_hours: int = 24,
    ):
        """Initialize with optional database connection.

        Args:
            db: Database connection for log access.
                If None, this stage will be skipped.
            max_tokens: Maximum tokens to allocate for logs context.
            log_window_hours: How far back to look for logs.
        """
        self._db = db
        self.max_tokens = max_tokens
        self.log_window_hours = log_window_hours

    @property
    def name(self) -> str:
        return "logs_context"

    def _is_debugging_task(self, task: Task) -> bool:
        """Determine if a task is debugging-related.

        Uses keyword matching on the task title and description
        to determine relevance.
        """
        text = f"{task.title} {task.description or ''}".lower()
        return any(keyword in text for keyword in self.DEBUG_KEYWORDS)

    def _calculate_relevance_score(self, task: Task) -> float:
        """Calculate a relevance score for logs context (0.0 - 1.0).

        Per docs/04-context-enrichment.md, logs have a high threshold (0.7).
        """
        text = f"{task.title} {task.description or ''}".lower()

        # Count keyword hits
        hits = sum(1 for keyword in self.DEBUG_KEYWORDS if keyword in text)

        # Score based on number of hits (normalize to 0-1)
        score = min(hits / 3, 1.0)  # 3+ keywords = max score

        # Boost for explicit debugging words
        explicit_debug_terms = {"debug", "error", "fix", "bug", "crash"}
        if any(term in text for term in explicit_debug_terms):
            score = max(score, 0.8)

        return score

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build logs context for debugging tasks.

        Only fetches logs when the task appears to be debugging-related.
        Prioritizes error logs and includes relevant context.
        """
        if self._db is None:
            return None

        # Check if task is debugging-related
        relevance = self._calculate_relevance_score(task)
        if relevance < 0.5:  # Not debugging-related enough
            logger.debug("Task %s doesn't appear debugging-related (score=%.2f)", task.id, relevance)
            return None

        try:
            from datetime import UTC, datetime, timedelta

            cutoff = datetime.now(UTC) - timedelta(hours=self.log_window_hours)
            cutoff_str = cutoff.isoformat()

            # First, try to get task-specific logs
            task_logs = await self._db.fetchall(
                """
                SELECT * FROM logs
                WHERE task_id = ?
                ORDER BY timestamp DESC
                LIMIT 50
                """,
                (task.id,),
            )

            # Also get project-level error logs (if project_id matches)
            project_logs = await self._db.fetchall(
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
            content = self._format_logs(logs)

            # Estimate tokens (rough: ~4 chars per token)
            tokens_estimate = len(content) // 4

            # Truncate if exceeds budget
            if tokens_estimate > self.max_tokens:
                # Calculate how many chars we can keep
                max_chars = self.max_tokens * 4
                content = content[:max_chars] + "\n\n... (logs truncated)"
                tokens_estimate = self.max_tokens

            sources = [f"logs:{len(logs)} entries"]

            logger.info(
                "Built logs context: %d entries, ~%d tokens for task %s",
                len(logs),
                tokens_estimate,
                task.id,
            )

            return StageResult(
                content=content,
                tokens_estimate=tokens_estimate,
                sources=sources,
            )

        except Exception as e:
            logger.warning("Failed to build logs context: %s", e)
            return None

    def _format_logs(self, logs: list) -> str:
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


class ResearchContextStage(BaseStage):
    """Stage 8: Research context from prior agent outputs.

    Per docs/04-context-enrichment.md section 2, this stage provides:
    - Prior agent task outputs (when task is related)
    - Task completion summaries
    - Related exploration/spike results

    Uses keyword-based matching to find related completed tasks.
    """

    # Keywords that increase relatedness between tasks
    TECHNICAL_KEYWORDS = {
        # API & web
        "api", "endpoint", "route", "routes", "controller", "service",
        "rest", "graphql", "request", "response", "http", "https",
        # Data
        "model", "schema", "database", "migration", "query", "sql",
        "repository", "entity", "table", "column", "field",
        # Testing
        "test", "tests", "mock", "fixture", "assertion", "coverage",
        "unit", "integration", "e2e", "spec",
        # Auth & security
        "auth", "authentication", "authorization", "jwt", "oauth",
        "token", "tokens", "login", "logout", "session", "password",
        "security", "vulnerability", "xss", "csrf", "injection",
        # Error handling
        "error", "errors", "exception", "handler", "middleware", "validator",
        "validation", "validate",
        # Caching & storage
        "cache", "caching", "redis", "memcached", "storage",
        # Async & workers
        "queue", "worker", "workers", "job", "task", "scheduler", "async",
        # Config
        "config", "configuration", "environment", "settings", "variable",
        # DevOps
        "deploy", "deployment", "ci", "cd", "build", "docker", "kubernetes",
        "container", "image", "pipeline",
        # Frontend
        "frontend", "component", "components", "hook", "hooks", "state", "redux",
        "react", "vue", "angular", "ui", "ux",
        # Performance
        "performance", "optimization", "profiling", "memory", "cpu",
        # Implementation patterns
        "implement", "implementation", "refactor", "update", "add", "fix",
        "create", "remove", "delete",
    }

    def __init__(
        self,
        db: Database | None = None,
        max_tokens: int = 4000,
        max_results: int = 5,
        min_relevance_score: float = 0.3,
    ):
        """Initialize with optional database connection.

        Args:
            db: Database connection for task output access.
                If None, this stage will be skipped.
            max_tokens: Maximum tokens to allocate for research context.
            max_results: Maximum number of related tasks to include.
            min_relevance_score: Minimum relevance score threshold (0-1).
        """
        self._db = db
        self.max_tokens = max_tokens
        self.max_results = max_results
        self.min_relevance_score = min_relevance_score

    @property
    def name(self) -> str:
        return "research_context"

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract relevant keywords from text."""
        if not text:
            return set()

        text_lower = text.lower()
        words = set(text_lower.split())

        # Find technical keywords that appear in the text
        return words & self.TECHNICAL_KEYWORDS

    def _calculate_relevance(
        self,
        current_keywords: set[str],
        current_title: str,
        candidate_title: str,
        candidate_description: str,
    ) -> float:
        """Calculate relevance score between current task and candidate.

        Uses Jaccard similarity on keywords plus title word overlap.
        """
        # Extract keywords from candidate
        candidate_text = f"{candidate_title} {candidate_description or ''}"
        candidate_keywords = self._extract_keywords(candidate_text)

        if not current_keywords and not candidate_keywords:
            return 0.0

        # Jaccard similarity on technical keywords
        intersection = current_keywords & candidate_keywords
        union = current_keywords | candidate_keywords

        keyword_score = len(intersection) / len(union) if union else 0.0

        # Title word overlap (non-stopword)
        current_title_words = set(current_title.lower().split()) - {
            "a", "an", "the", "to", "for", "in", "on", "with", "and", "or", "of",
        }
        candidate_title_words = set(candidate_title.lower().split()) - {
            "a", "an", "the", "to", "for", "in", "on", "with", "and", "or", "of",
        }

        if current_title_words and candidate_title_words:
            title_intersection = current_title_words & candidate_title_words
            title_union = current_title_words | candidate_title_words
            title_score = len(title_intersection) / len(title_union)
        else:
            title_score = 0.0

        # Combined score (keywords weighted higher)
        return keyword_score * 0.7 + title_score * 0.3

    async def process(self, task: Task, project: Project) -> StageResult | None:
        """Build research context from prior task outputs.

        Queries completed tasks in the same project and includes
        output summaries from semantically related tasks.
        """
        if self._db is None:
            return None

        try:
            # Get completed tasks with output summaries
            completed_tasks = await self._db.fetchall(
                """
                SELECT t.id, t.title, t.description, t.type,
                       t.completed_at, sm.output_summary
                FROM tasks t
                LEFT JOIN session_metrics sm ON t.id = sm.task_id AND sm.success = 1
                WHERE t.project_id = ?
                  AND t.id != ?
                  AND t.status = 'done'
                  AND t.type IN ('task', 'subtask')
                ORDER BY t.completed_at DESC
                LIMIT 50
                """,
                (str(project.id), task.id),
            )

            if not completed_tasks:
                logger.debug("No completed tasks found for project %s", project.id)
                return None

            # Extract keywords from current task
            current_text = f"{task.title} {task.description or ''}"
            current_keywords = self._extract_keywords(current_text)

            # Score and rank related tasks
            scored_tasks = []
            for row in completed_tasks:
                relevance = self._calculate_relevance(
                    current_keywords,
                    task.title,
                    row["title"],
                    row["description"],
                )
                if relevance >= self.min_relevance_score:
                    scored_tasks.append((row, relevance))

            # Sort by relevance, take top N
            scored_tasks.sort(key=lambda x: x[1], reverse=True)
            top_tasks = scored_tasks[: self.max_results]

            if not top_tasks:
                logger.debug("No related tasks found for task %s", task.id)
                return None

            # Format for context
            content = self._format_research_context(top_tasks)

            # Estimate tokens
            tokens_estimate = len(content) // 4

            # Truncate if exceeds budget
            if tokens_estimate > self.max_tokens:
                max_chars = self.max_tokens * 4
                content = content[:max_chars] + "\n\n... (research context truncated)"
                tokens_estimate = self.max_tokens

            sources = [f"research:{len(top_tasks)} related tasks"]

            logger.info(
                "Built research context: %d related tasks, ~%d tokens for task %s",
                len(top_tasks),
                tokens_estimate,
                task.id,
            )

            return StageResult(
                content=content,
                tokens_estimate=tokens_estimate,
                sources=sources,
            )

        except Exception as e:
            logger.warning("Failed to build research context: %s", e)
            return None

    def _format_research_context(self, scored_tasks: list[tuple[dict, float]]) -> str:
        """Format related task outputs for prompt inclusion."""
        parts = ["## Prior Research & Related Work", ""]

        for row, relevance in scored_tasks:
            task_id = row["id"]
            title = row["title"]
            task_type = row["type"]
            output_summary = row["output_summary"]
            completed_at = row["completed_at"]

            parts.append(f"### {title}")
            parts.append(f"- ID: {task_id} ({task_type})")
            parts.append(f"- Completed: {completed_at}")
            parts.append(f"- Relevance: {relevance:.0%}")

            if output_summary:
                parts.append(f"\n**Summary:** {output_summary}")
            elif row["description"]:
                # Fall back to description if no output summary
                desc = row["description"][:500]
                if len(row["description"]) > 500:
                    desc += "..."
                parts.append(f"\n**Description:** {desc}")

            parts.append("")

        return "\n".join(parts)


class RefinementStage(BaseStage):
    """Stage 9: Refinement and safety guardrails."""

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
