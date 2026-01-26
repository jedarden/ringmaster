"""Decompose large tasks into smaller, atomic subtasks.

Uses heuristic rules (no LLM) to detect when a task is too large and
break it down into manageable pieces.
"""

import re
from dataclasses import dataclass

from ringmaster.creator.parser import ActionType, TaskCandidate


@dataclass
class DecompositionResult:
    """Result of attempting to decompose a task."""

    should_decompose: bool
    reason: str
    subtasks: list[TaskCandidate]


# Signals that suggest a task is too large
SIZE_SIGNALS = {
    "description_length": 2000,  # Characters
    "multiple_components": 3,  # Distinct components mentioned
    "multiple_concerns": 2,  # Separate concerns in one task
    "conjunction_count": 3,  # Number of "and" conjunctions
}

# Keywords that suggest multiple components
COMPONENT_KEYWORDS = [
    r"\bmodule\b",
    r"\bcomponent\b",
    r"\bservice\b",
    r"\bendpoint\b",
    r"\bcontroller\b",
    r"\brepository\b",
    r"\bhandler\b",
    r"\brouter\b",
    r"\bschema\b",
    r"\bmigration\b",
    r"\btest\b",
    r"\bintegration\b",
]

# Keywords suggesting multiple concerns
CONCERN_KEYWORDS = [
    r"\band\s+also\b",
    r"\badditionally\b",
    r"\bas\s+well\s+as\b",
    r"\bplus\b",
    r"\bmultiple\b",
    r"\bseveral\b",
    r"\bboth\b",
    r"\bvarious\b",
]


def count_components(text: str) -> int:
    """Count how many distinct components are mentioned."""
    text_lower = text.lower()
    count = sum(1 for kw in COMPONENT_KEYWORDS if re.search(kw, text_lower))
    return count


def count_concerns(text: str) -> int:
    """Count indicators of multiple concerns."""
    text_lower = text.lower()
    count = sum(1 for kw in CONCERN_KEYWORDS if re.search(kw, text_lower))
    return count


def is_too_large(candidate: TaskCandidate) -> tuple[bool, list[str]]:
    """Determine if a task candidate is too large.

    Returns (is_too_large, list of reasons)
    """
    text = candidate.raw_text
    reasons: list[str] = []

    # Check each signal
    if len(text) > SIZE_SIGNALS["description_length"]:
        reasons.append(f"Description exceeds {SIZE_SIGNALS['description_length']} characters")

    component_count = count_components(text)
    if component_count > SIZE_SIGNALS["multiple_components"]:
        reasons.append(f"Contains {component_count} distinct components")

    concern_count = count_concerns(text)
    if concern_count > SIZE_SIGNALS["multiple_concerns"]:
        reasons.append(f"Contains {concern_count} multiple-concern indicators")

    conjunction_count = text.lower().count(" and ")
    if conjunction_count > SIZE_SIGNALS["conjunction_count"]:
        reasons.append(f"Contains {conjunction_count} 'and' conjunctions")

    # Threshold: 2+ signals means too large
    return len(reasons) >= 2, reasons


def extract_subtasks_by_list(text: str) -> list[str]:
    """Extract subtasks from numbered or bulleted lists."""
    subtasks: list[str] = []

    # Match numbered items (1. or 1) format)
    numbered = re.findall(r"\d+[.)]\s*([^\n]+)", text)
    subtasks.extend(numbered)

    # Match bulleted items (- or * format)
    bulleted = re.findall(r"[-*]\s+([^\n]+)", text)
    subtasks.extend(bulleted)

    return [s.strip() for s in subtasks if s.strip()]


def extract_subtasks_by_conjunction(text: str) -> list[str]:
    """Extract subtasks by splitting on conjunctions."""
    # Split on common separators
    patterns = [
        r"\s+and\s+then\s+",
        r"\s+then\s+",
        r"\s+after\s+that\s+",
        r"\s+finally\s+",
        r"[;]\s+",
    ]

    segments = [text]
    for pattern in patterns:
        new_segments = []
        for segment in segments:
            parts = re.split(pattern, segment, flags=re.IGNORECASE)
            new_segments.extend(parts)
        segments = new_segments

    return [s.strip() for s in segments if len(s.strip()) > 10]


def extract_subtasks_by_components(text: str) -> list[str]:
    """Extract subtasks based on component mentions."""
    subtasks: list[str] = []
    text_lower = text.lower()

    # Common patterns for component-based work
    patterns = [
        (r"(create|implement|add|build)\s+(a|an|the)?\s*(\w+\s+)?(module|component|service)", "Create {match}"),
        (r"(add|implement|create)\s+(a|an|the)?\s*(\w+\s+)?(endpoint|route|api)", "Implement {match}"),
        (r"(write|add|create)\s+(the\s+)?(tests?|specs?)", "Write tests"),
        (r"(update|modify)\s+(the\s+)?(schema|database|migration)", "Update schema/migration"),
        (r"(add|update|modify)\s+(the\s+)?(configuration|config)", "Update configuration"),
        (r"(integrate|connect)\s+(with\s+)?(\w+)", "Integrate with {match}"),
    ]

    for pattern, template in patterns:
        match = re.search(pattern, text_lower)
        if match:
            # Create a subtask title from the match
            matched_text = match.group(0)
            subtask = template.replace("{match}", matched_text)
            if subtask not in subtasks:
                subtasks.append(subtask)

    return subtasks


def infer_standard_subtasks(action_type: ActionType, target: str) -> list[str]:
    """Infer standard subtasks based on action type.

    For example, implementing a feature typically includes:
    1. Set up structure
    2. Implement core logic
    3. Write tests
    4. Add documentation
    """
    subtasks: list[str] = []

    if action_type == ActionType.CREATE:
        subtasks = [
            f"Set up {target} module structure",
            f"Implement core {target} logic",
            f"Write unit tests for {target}",
            f"Add integration tests for {target}",
        ]
    elif action_type == ActionType.FIX:
        subtasks = [
            f"Investigate {target} issue",
            f"Implement fix for {target}",
            f"Add regression test for {target}",
        ]
    elif action_type == ActionType.UPDATE:
        subtasks = [
            f"Analyze current {target} implementation",
            f"Implement {target} updates",
            f"Update tests for {target}",
        ]
    elif action_type == ActionType.TEST:
        subtasks = [
            f"Analyze {target} test coverage",
            f"Write missing tests for {target}",
            f"Fix failing tests for {target}",
        ]

    return subtasks


def decompose_candidate(candidate: TaskCandidate) -> DecompositionResult:
    """Decompose a task candidate into subtasks if needed.

    Returns a DecompositionResult with subtasks if the candidate is too large,
    or an empty list if decomposition is not needed.
    """
    too_large, reasons = is_too_large(candidate)

    if not too_large:
        return DecompositionResult(
            should_decompose=False,
            reason="Task is appropriately sized",
            subtasks=[],
        )

    text = candidate.raw_text
    subtask_texts: list[str] = []

    # Try extraction methods in order of specificity
    # 1. Explicit lists
    list_subtasks = extract_subtasks_by_list(text)
    if list_subtasks:
        subtask_texts.extend(list_subtasks)

    # 2. Component-based extraction
    if not subtask_texts:
        component_subtasks = extract_subtasks_by_components(text)
        if component_subtasks:
            subtask_texts.extend(component_subtasks)

    # 3. Conjunction-based splitting
    if not subtask_texts:
        conjunction_subtasks = extract_subtasks_by_conjunction(text)
        if len(conjunction_subtasks) > 1:
            subtask_texts.extend(conjunction_subtasks)

    # 4. Infer standard subtasks based on action type
    if not subtask_texts and candidate.target:
        inferred = infer_standard_subtasks(candidate.action_type, candidate.target)
        if inferred:
            subtask_texts.extend(inferred)

    # Convert text to TaskCandidate objects
    subtasks: list[TaskCandidate] = []
    for i, text in enumerate(subtask_texts):
        from ringmaster.creator.parser import detect_action_type, extract_target

        action_type, confidence = detect_action_type(text)
        target = extract_target(text, action_type)

        subtask = TaskCandidate(
            raw_text=text,
            action_type=action_type if action_type != ActionType.UNKNOWN else candidate.action_type,
            target=target if target else text[:50],
            order_hint=i * 10,
            confidence=confidence,
        )
        subtasks.append(subtask)

    return DecompositionResult(
        should_decompose=True,
        reason="; ".join(reasons),
        subtasks=subtasks,
    )
