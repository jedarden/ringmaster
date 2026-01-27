"""Model routing based on task complexity.

Per docs/08-open-architecture.md section 11:
- Deterministic heuristics for cold start (no LLM calls)
- Complexity estimation based on file count, keywords, task type
- Model selection mapped from complexity level

Future: Reflexion-based learning from task outcomes (reasoning bank).
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ringmaster.domain.models import Epic, Subtask, Task


class TaskComplexity(str, Enum):
    """Task complexity levels for model routing."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ModelTier(str, Enum):
    """Model tiers for routing decisions."""

    FAST = "fast"  # claude-haiku, gpt-4o-mini
    BALANCED = "balanced"  # claude-sonnet, gpt-4o
    POWERFUL = "powerful"  # claude-opus, o1


@dataclass
class ComplexitySignals:
    """Signals used to determine task complexity."""

    file_count: int
    dependency_count: int
    description_length: int
    simple_keyword_matches: int
    complex_keyword_matches: int
    is_epic: bool
    is_subtask: bool
    is_critical: bool
    raw_score: int


@dataclass
class RoutingResult:
    """Result of model routing decision."""

    complexity: TaskComplexity
    tier: ModelTier
    signals: ComplexitySignals
    reasoning: str
    suggested_models: list[str]


# Keywords that indicate simpler tasks
SIMPLE_KEYWORDS = {
    "typo",
    "rename",
    "format",
    "lint",
    "comment",
    "todo",
    "fixme",
    "update comment",
    "fix typo",
    "add comment",
    "remove unused",
    "cleanup",
    "whitespace",
    "indent",
}

# Keywords that indicate complex tasks
COMPLEX_KEYWORDS = {
    "architect",
    "refactor",
    "migrate",
    "security",
    "auth",
    "authentication",
    "authorization",
    "database",
    "schema",
    "api design",
    "breaking change",
    "redesign",
    "rewrite",
    "performance",
    "optimize",
    "scale",
    "distributed",
    "concurrent",
    "async",
    "infrastructure",
    "deploy",
    "ci/cd",
    "integration",
}

# Model suggestions per tier
MODEL_SUGGESTIONS = {
    ModelTier.FAST: [
        "claude-3-haiku-20240307",
        "gpt-4o-mini",
    ],
    ModelTier.BALANCED: [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "gpt-4o",
    ],
    ModelTier.POWERFUL: [
        "claude-opus-4-20250514",
        "o1",
        "o1-preview",
    ],
}


def _extract_text(task: "Task | Epic | Subtask") -> str:
    """Extract searchable text from a task."""
    parts = [task.title]
    if task.description:
        parts.append(task.description)
    return " ".join(parts).lower()


def _count_keyword_matches(text: str, keywords: set[str]) -> int:
    """Count how many keywords appear in the text."""
    count = 0
    for kw in keywords:
        if kw in text:
            count += 1
    return count


def _count_suggested_files(task: "Task | Epic | Subtask") -> int:
    """Estimate file count from task description."""
    # Look for file patterns in description
    text = _extract_text(task)

    # Match common file patterns
    file_patterns = [
        r"\.py\b",
        r"\.ts\b",
        r"\.tsx\b",
        r"\.js\b",
        r"\.jsx\b",
        r"\.rs\b",
        r"\.go\b",
        r"\.java\b",
        r"\.rb\b",
        r"\.cpp\b",
        r"\.c\b",
        r"\.h\b",
        r"\.sql\b",
        r"\.yaml\b",
        r"\.yml\b",
        r"\.json\b",
        r"\.md\b",
    ]

    file_count = 0
    for pattern in file_patterns:
        file_count += len(re.findall(pattern, text))

    # Look for explicit file mentions
    file_mention_pattern = r"(?:file|module|component|class)s?\s*:?\s*\d+"
    explicit_mentions = re.findall(file_mention_pattern, text)
    for mention in explicit_mentions:
        nums = re.findall(r"\d+", mention)
        if nums:
            file_count = max(file_count, int(nums[0]))

    return file_count


def estimate_complexity(task: "Task | Epic | Subtask") -> ComplexitySignals:
    """
    Estimate task complexity using DETERMINISTIC heuristics.
    No LLM calls - pure rule-based scoring.

    Returns the raw signals for transparency.
    """
    from ringmaster.domain.enums import Priority, TaskType

    text = _extract_text(task)
    score = 0

    # File count signals
    file_count = _count_suggested_files(task)
    if file_count == 0:
        score += 0  # Unknown, assume moderate
    elif file_count == 1:
        score += 0  # Single file = simple
    elif file_count <= 3:
        score += 1  # Few files = moderate
    else:
        score += 2  # Many files = complex

    # Keyword signals
    simple_matches = _count_keyword_matches(text, SIMPLE_KEYWORDS)
    complex_matches = _count_keyword_matches(text, COMPLEX_KEYWORDS)

    if simple_matches > 0:
        score -= simple_matches  # Each simple keyword decreases complexity
    score += complex_matches  # Each complex keyword increases complexity

    # Dependency signals
    dependency_count = 0
    if hasattr(task, "child_ids"):
        dependency_count = len(task.child_ids)

    if dependency_count > 2:
        score += 1  # Many dependencies = integration work

    # Task type signals
    is_epic = task.type == TaskType.EPIC
    is_subtask = task.type == TaskType.SUBTASK

    if is_epic:
        score += 2  # Epics are inherently complex
    elif is_subtask:
        score -= 1  # Subtasks are granular

    # Priority signals
    is_critical = task.priority == Priority.P0
    if is_critical:
        score += 1  # Critical often means complex

    # Description length signals
    desc_length = len(task.description or "")
    if desc_length > 2000:
        score += 1  # Long descriptions often indicate complexity

    return ComplexitySignals(
        file_count=file_count,
        dependency_count=dependency_count,
        description_length=desc_length,
        simple_keyword_matches=simple_matches,
        complex_keyword_matches=complex_matches,
        is_epic=is_epic,
        is_subtask=is_subtask,
        is_critical=is_critical,
        raw_score=score,
    )


def complexity_from_score(score: int) -> TaskComplexity:
    """Map raw score to complexity level."""
    if score <= 0:
        return TaskComplexity.SIMPLE
    elif score <= 2:
        return TaskComplexity.MODERATE
    else:
        return TaskComplexity.COMPLEX


def tier_from_complexity(
    complexity: TaskComplexity,
    task_type: str | None = None,
) -> ModelTier:
    """Map complexity to model tier, with task-type adjustments."""
    # Base mapping
    if complexity == TaskComplexity.SIMPLE:
        tier = ModelTier.FAST
    elif complexity == TaskComplexity.MODERATE:
        tier = ModelTier.BALANCED
    else:
        tier = ModelTier.POWERFUL

    # Task type adjustments
    if task_type == "research":
        # Research benefits from faster iteration, doesn't need most powerful
        if tier == ModelTier.POWERFUL:
            tier = ModelTier.BALANCED
    elif task_type == "validation":
        # Validation needs thoroughness but not creativity
        tier = ModelTier.BALANCED

    return tier


def select_model_for_task(task: "Task | Epic | Subtask") -> RoutingResult:
    """
    Route task to appropriate model based on complexity.

    This is a deterministic cold-start implementation.
    Future: Integrate with reasoning bank for learned routing.
    """
    # Get complexity signals
    signals = estimate_complexity(task)
    complexity = complexity_from_score(signals.raw_score)

    # Get task type if available
    task_type = None
    if hasattr(task, "type"):
        task_type = str(task.type.value) if hasattr(task.type, "value") else str(task.type)

    # Map to model tier
    tier = tier_from_complexity(complexity, task_type)

    # Build reasoning explanation
    reasons = []
    if signals.file_count > 0:
        reasons.append(f"{signals.file_count} files detected")
    if signals.simple_keyword_matches > 0:
        reasons.append(f"{signals.simple_keyword_matches} simple keywords")
    if signals.complex_keyword_matches > 0:
        reasons.append(f"{signals.complex_keyword_matches} complex keywords")
    if signals.is_epic:
        reasons.append("epic type (inherently complex)")
    if signals.is_subtask:
        reasons.append("subtask (granular)")
    if signals.is_critical:
        reasons.append("P0 priority")

    reasoning = f"Score {signals.raw_score}: " + ", ".join(reasons) if reasons else f"Score {signals.raw_score}: default assessment"

    return RoutingResult(
        complexity=complexity,
        tier=tier,
        signals=signals,
        reasoning=reasoning,
        suggested_models=MODEL_SUGGESTIONS[tier],
    )


def get_model_for_worker_type(
    tier: ModelTier,
    worker_type: str,
) -> str | None:
    """Get the recommended model for a worker type at a given tier.

    Returns the model ID to use, or None if no recommendation.
    """
    # Map worker types to their preferred models at each tier
    worker_models = {
        "claude-code": {
            ModelTier.FAST: "claude-3-haiku-20240307",
            ModelTier.BALANCED: "claude-sonnet-4-20250514",
            ModelTier.POWERFUL: "claude-opus-4-20250514",
        },
        "aider": {
            ModelTier.FAST: "gpt-4o-mini",
            ModelTier.BALANCED: "claude-sonnet-4-20250514",
            ModelTier.POWERFUL: "claude-opus-4-20250514",
        },
        "codex": {
            ModelTier.FAST: "gpt-4o-mini",
            ModelTier.BALANCED: "gpt-4o",
            ModelTier.POWERFUL: "o1",
        },
        "goose": {
            ModelTier.FAST: "claude-3-haiku-20240307",
            ModelTier.BALANCED: "claude-sonnet-4-20250514",
            ModelTier.POWERFUL: "claude-opus-4-20250514",
        },
    }

    if worker_type in worker_models:
        return worker_models[worker_type].get(tier)

    return None
