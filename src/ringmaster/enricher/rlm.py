"""Recursive Language Model (RLM) summarization for context compression.

Based on docs/04-context-enrichment.md:
- Hierarchical chat history compression
- Decision extraction and preservation
- Token budget management
"""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from ringmaster.db import ChatRepository, Database
from ringmaster.domain import ChatMessage, Summary

logger = logging.getLogger(__name__)

# Configuration defaults
DEFAULT_RECENT_VERBATIM = 10  # Keep last N messages verbatim
DEFAULT_SUMMARY_THRESHOLD = 20  # Start summarizing after this many messages
DEFAULT_CHUNK_SIZE = 10  # Messages per summary chunk
DEFAULT_MAX_CONTEXT_TOKENS = 4000  # Max tokens for history context


@dataclass
class HistoryContext:
    """Assembled history context for prompt enrichment."""

    recent_messages: list[ChatMessage]
    summaries: list[Summary]
    key_decisions: list[str]
    total_messages: int
    estimated_tokens: int


@dataclass
class CompressionConfig:
    """Configuration for RLM compression."""

    recent_verbatim: int = DEFAULT_RECENT_VERBATIM
    summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD
    chunk_size: int = DEFAULT_CHUNK_SIZE
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS


class RLMSummarizer:
    """Recursive Language Model summarizer for chat history compression.

    This implements a heuristic-based summarization approach:
    1. Keep recent messages verbatim (configurable count)
    2. Summarize older messages in chunks
    3. Extract and preserve key decisions

    For production, the summarize_chunk method could be replaced with
    an actual LLM call, but the current implementation uses heuristics
    to avoid external dependencies.
    """

    def __init__(
        self,
        db: Database,
        config: CompressionConfig | None = None,
    ):
        self.db = db
        self.chat_repo = ChatRepository(db)
        self.config = config or CompressionConfig()

    async def get_history_context(
        self,
        project_id: UUID,
        task_id: str | None = None,
    ) -> HistoryContext:
        """Get compressed history context for a task.

        Returns recent messages verbatim and summaries of older messages,
        fitting within the configured token budget.
        """
        # Get total message count
        total_count = await self.chat_repo.get_message_count(project_id, task_id)

        if total_count == 0:
            return HistoryContext(
                recent_messages=[],
                summaries=[],
                key_decisions=[],
                total_messages=0,
                estimated_tokens=0,
            )

        # Get recent messages verbatim
        recent = await self.chat_repo.get_recent_messages(
            project_id,
            count=self.config.recent_verbatim,
            task_id=task_id,
        )

        # Get existing summaries
        summaries = await self.chat_repo.get_summaries(project_id, task_id)

        # Check if we need to create new summaries
        if total_count > self.config.summary_threshold:
            summaries = await self._ensure_summaries_current(
                project_id, task_id, total_count, recent
            )

        # Extract key decisions from all content
        key_decisions = self._extract_decisions_from_context(recent, summaries)

        # Estimate tokens
        estimated_tokens = self._estimate_tokens(recent, summaries)

        return HistoryContext(
            recent_messages=recent,
            summaries=summaries,
            key_decisions=key_decisions,
            total_messages=total_count,
            estimated_tokens=estimated_tokens,
        )

    async def _ensure_summaries_current(
        self,
        project_id: UUID,
        task_id: str | None,
        total_count: int,
        recent_messages: list[ChatMessage],
    ) -> list[Summary]:
        """Ensure summaries cover all older messages."""
        summaries = await self.chat_repo.get_summaries(project_id, task_id)

        # Determine the range of messages that need summarizing
        # (everything except recent verbatim messages)
        if not recent_messages:
            return summaries

        # Find the cutoff - messages before the first recent message
        first_recent_id = recent_messages[0].id if recent_messages[0].id else 0

        # Check what range is already covered
        covered_end = 0
        if summaries:
            covered_end = max(s.message_range_end for s in summaries)

        # Get messages that need summarizing
        if covered_end < first_recent_id - 1:
            unsummarized = await self.chat_repo.get_message_range(
                covered_end + 1, first_recent_id - 1
            )

            if len(unsummarized) >= self.config.chunk_size:
                # Create new summaries for unsummarized messages
                new_summaries = await self._create_summaries_for_messages(
                    project_id, task_id, unsummarized
                )
                summaries.extend(new_summaries)

        return summaries

    async def _create_summaries_for_messages(
        self,
        project_id: UUID,
        task_id: str | None,
        messages: list[ChatMessage],
    ) -> list[Summary]:
        """Create summaries for a list of messages in chunks."""
        new_summaries: list[Summary] = []

        # Process in chunks
        for i in range(0, len(messages), self.config.chunk_size):
            chunk = messages[i : i + self.config.chunk_size]
            if not chunk:
                continue

            # Get message IDs for the range
            start_id = chunk[0].id or 0
            end_id = chunk[-1].id or 0

            # Generate summary text
            summary_text = self._summarize_chunk(chunk)
            key_decisions = self._extract_decisions(chunk)

            # Create and store summary
            summary = Summary(
                project_id=project_id,
                task_id=task_id,
                message_range_start=start_id,
                message_range_end=end_id,
                summary=summary_text,
                key_decisions=key_decisions,
                token_count=len(summary_text) // 4,  # Rough estimate
            )
            summary = await self.chat_repo.create_summary(summary)
            new_summaries.append(summary)

        return new_summaries

    def _summarize_chunk(self, messages: list[ChatMessage]) -> str:
        """Summarize a chunk of messages.

        This is a heuristic implementation. For production use,
        this could call an LLM for better summarization.
        """
        if not messages:
            return ""

        # Extract key information from messages
        topics: set[str] = set()
        actions: list[str] = []
        questions: list[str] = []

        for msg in messages:
            content = msg.content.lower()

            # Extract mentioned files/paths
            file_patterns = re.findall(r'[`"\']?[\w/]+\.(py|ts|js|rs|md|sql)[`"\']?', content)
            topics.update(file_patterns)

            # Extract action keywords
            if msg.role == "user":
                if "?" in msg.content:
                    # Truncate long questions
                    q = msg.content.split("?")[0][:100]
                    questions.append(q)
            elif msg.role == "assistant":
                # Look for action patterns
                action_patterns = [
                    r"(created|updated|modified|deleted|added|removed)\s+\S+",
                    r"(fixed|implemented|resolved)\s+\w+",
                ]
                for pattern in action_patterns:
                    matches = re.findall(pattern, content[:500])
                    actions.extend(matches[:3])

        # Build summary
        parts = []

        if topics:
            parts.append(f"Files discussed: {', '.join(list(topics)[:5])}")

        if questions:
            parts.append(f"Questions asked: {'; '.join(questions[:3])}")

        if actions:
            parts.append(f"Actions taken: {', '.join(actions[:5])}")

        if not parts:
            # Fallback: create a generic summary
            msg_count = len(messages)
            roles = {m.role for m in messages}
            parts.append(f"Conversation ({msg_count} messages, roles: {', '.join(roles)})")

        return " | ".join(parts)

    def _extract_decisions(self, messages: list[ChatMessage]) -> list[str]:
        """Extract key decisions from messages.

        Looks for decision patterns like:
        - "decided to..."
        - "we'll use..."
        - "going with..."
        - explicit decisions markers
        """
        decisions: list[str] = []
        decision_patterns = [
            r"decided\s+to\s+([^.!?\n]+)",
            r"we(?:'ll| will)\s+use\s+([^.!?\n]+)",
            r"going\s+with\s+([^.!?\n]+)",
            r"choice:\s*([^.!?\n]+)",
            r"decision:\s*([^.!?\n]+)",
        ]

        for msg in messages:
            content = msg.content.lower()
            for pattern in decision_patterns:
                matches = re.findall(pattern, content)
                for match in matches[:2]:  # Limit per message
                    decision = match.strip()[:150]  # Truncate
                    if decision and decision not in decisions:
                        decisions.append(decision)

        return decisions[:10]  # Limit total decisions

    def _extract_decisions_from_context(
        self,
        recent: list[ChatMessage],
        summaries: list[Summary],
    ) -> list[str]:
        """Extract all key decisions from context."""
        decisions: list[str] = []

        # From summaries
        for summary in summaries:
            decisions.extend(summary.key_decisions)

        # From recent messages
        decisions.extend(self._extract_decisions(recent))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for d in decisions:
            if d not in seen:
                seen.add(d)
                unique.append(d)

        return unique[:15]  # Limit total

    def _estimate_tokens(
        self,
        messages: list[ChatMessage],
        summaries: list[Summary],
    ) -> int:
        """Estimate token count for the assembled context."""
        total = 0

        # Messages (~4 chars per token)
        for msg in messages:
            total += len(msg.content) // 4

        # Summaries
        for summary in summaries:
            total += len(summary.summary) // 4

        return total

    def format_for_prompt(self, context: HistoryContext) -> str:
        """Format history context for inclusion in a prompt."""
        parts: list[str] = []

        # Add header
        parts.append("## Conversation History")
        parts.append(f"(Total: {context.total_messages} messages)")
        parts.append("")

        # Add key decisions if any
        if context.key_decisions:
            parts.append("### Key Decisions")
            for i, decision in enumerate(context.key_decisions, 1):
                parts.append(f"{i}. {decision}")
            parts.append("")

        # Add summaries of older messages
        if context.summaries:
            parts.append("### Summary of Earlier Discussion")
            for summary in context.summaries:
                parts.append(f"- {summary.summary}")
            parts.append("")

        # Add recent messages verbatim
        if context.recent_messages:
            parts.append("### Recent Messages")
            for msg in context.recent_messages:
                role_label = msg.role.capitalize()
                # Truncate very long messages
                content = msg.content[:2000]
                if len(msg.content) > 2000:
                    content += "... (truncated)"
                parts.append(f"**{role_label}:** {content}")
                parts.append("")

        return "\n".join(parts)


# Convenience function for one-shot usage
async def get_history_context(
    db: Database,
    project_id: UUID,
    task_id: str | None = None,
    config: CompressionConfig | None = None,
) -> HistoryContext:
    """Get compressed history context for a project/task."""
    summarizer = RLMSummarizer(db, config)
    return await summarizer.get_history_context(project_id, task_id)
