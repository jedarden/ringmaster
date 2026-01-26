"""Parse user input to extract actionable task candidates.

Uses heuristic-based parsing (no LLM) to identify:
- Action verbs (implement, add, fix, refactor, etc.)
- Targets (nouns/phrases following actions)
- Conjunctions that indicate multiple tasks
- Ordering signals for dependencies
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class ActionType(Enum):
    """Type of action detected in the input."""

    CREATE = "create"  # implement, add, build, create
    FIX = "fix"  # fix, repair, debug, resolve
    UPDATE = "update"  # update, modify, change, refactor
    REMOVE = "remove"  # remove, delete, deprecate
    TEST = "test"  # test, verify, validate
    DOCUMENT = "document"  # document, explain, describe
    INVESTIGATE = "investigate"  # investigate, analyze, explore
    UNKNOWN = "unknown"


# Action verb patterns grouped by type
ACTION_PATTERNS: dict[ActionType, list[str]] = {
    ActionType.CREATE: [
        r"\b(implement|add|build|create|make|write|develop|introduce)\b",
    ],
    ActionType.FIX: [
        r"\b(fix|repair|debug|resolve|patch|correct|address|handle)\b",
    ],
    ActionType.UPDATE: [
        r"\b(update|modify|change|refactor|improve|enhance|optimize|upgrade)\b",
    ],
    ActionType.REMOVE: [
        r"\b(remove|delete|deprecate|eliminate|drop|clean\s*up)\b",
    ],
    ActionType.TEST: [
        r"\b(test|verify|validate|check|ensure|confirm)\b",
    ],
    ActionType.DOCUMENT: [
        r"\b(document|explain|describe|write\s+docs?|add\s+comments?)\b",
    ],
    ActionType.INVESTIGATE: [
        r"\b(investigate|analyze|explore|research|look\s+into|examine)\b",
    ],
}

# Patterns for splitting multiple tasks
CONJUNCTION_PATTERNS = [
    r"\s+and\s+also\s+",
    r"\s+additionally[,]?\s+",
    r"\s+as\s+well\s+as\s+",
    r"\s+then\s+",
    r"\s+after\s+that[,]?\s+",
    r"\s+finally[,]?\s+",
    r"[.;]\s+",
    r"\n+",
    r"\d+[.)]\s+",  # Numbered lists
    r"[-*]\s+",  # Bullet points
]

# Patterns indicating ordering/dependencies
ORDERING_PATTERNS = [
    (r"\bfirst\b", 0),
    (r"\bbefore\b", -1),  # Relative: before means this comes after something
    (r"\bafter\b", 1),  # Relative: after means this depends on previous
    (r"\bthen\b", 1),
    (r"\bfinally\b", 100),  # High order = comes last
    (r"\blast\b", 100),
]


@dataclass
class TaskCandidate:
    """A potential task extracted from user input."""

    raw_text: str
    action_type: ActionType = ActionType.UNKNOWN
    target: str = ""
    order_hint: int = 0  # Lower = earlier in sequence
    confidence: float = 0.0  # How confident we are this is a real task

    def to_title(self) -> str:
        """Generate a title from the action and target."""
        if not self.target:
            return self.raw_text.strip()[:100]

        action_word = self._get_action_verb()
        return f"{action_word} {self.target}"[:100]

    def _get_action_verb(self) -> str:
        """Get the canonical action verb for this type."""
        verbs = {
            ActionType.CREATE: "Implement",
            ActionType.FIX: "Fix",
            ActionType.UPDATE: "Update",
            ActionType.REMOVE: "Remove",
            ActionType.TEST: "Test",
            ActionType.DOCUMENT: "Document",
            ActionType.INVESTIGATE: "Investigate",
            ActionType.UNKNOWN: "",
        }
        return verbs[self.action_type]


@dataclass
class ParsedInput:
    """Result of parsing user input."""

    original_text: str
    candidates: list[TaskCandidate] = field(default_factory=list)
    is_epic: bool = False  # True if this should be an epic with child tasks
    suggested_epic_title: str = ""


def detect_action_type(text: str) -> tuple[ActionType, float]:
    """Detect the action type from text.

    Returns (action_type, confidence)
    """
    text_lower = text.lower()

    for action_type, patterns in ACTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                # Higher confidence if action verb is at the start
                if re.match(r"^\s*" + pattern, text_lower, re.IGNORECASE):
                    return action_type, 0.9
                return action_type, 0.7

    return ActionType.UNKNOWN, 0.3


def extract_target(text: str, action_type: ActionType) -> str:
    """Extract the target (what to act on) from the text."""
    # Remove the action verb to get the target
    text_clean = text.strip()

    for patterns in ACTION_PATTERNS.values():
        for pattern in patterns:
            text_clean = re.sub(pattern, "", text_clean, flags=re.IGNORECASE)

    # Clean up articles and common filler words
    text_clean = re.sub(r"^\s*(a|an|the|some)\s+", "", text_clean, flags=re.IGNORECASE)
    text_clean = re.sub(r"\s+", " ", text_clean).strip()

    return text_clean


def detect_order_hint(text: str) -> int:
    """Detect ordering hints from the text.

    Returns an integer for sorting (lower = earlier).
    """
    text_lower = text.lower()

    for pattern, order in ORDERING_PATTERNS:
        if re.search(pattern, text_lower):
            return order

    return 50  # Middle of the road


def split_into_segments(text: str) -> list[str]:
    """Split input text into potential task segments."""
    segments = [text]

    # Apply splitting patterns
    for pattern in CONJUNCTION_PATTERNS:
        new_segments = []
        for segment in segments:
            parts = re.split(pattern, segment, flags=re.IGNORECASE)
            new_segments.extend([p.strip() for p in parts if p.strip()])
        segments = new_segments

    # Filter out segments that are too short to be tasks
    segments = [s for s in segments if len(s) >= 10]

    return segments


def is_likely_epic(text: str, candidate_count: int) -> bool:
    """Determine if the input should be treated as an epic.

    Criteria:
    - Multiple task candidates (3+)
    - Contains epic-like keywords
    - Long description with multiple components
    """
    epic_keywords = [
        r"\bsystem\b",
        r"\bfeature\b",
        r"\bservice\b",
        r"\bmodule\b",
        r"\bintegration\b",
        r"\bfull\b",
        r"\bcomplete\b",
        r"\bentire\b",
        r"\bwhole\b",
    ]

    text_lower = text.lower()

    # Multiple candidates suggests decomposition
    if candidate_count >= 3:
        return True

    # Epic keywords suggest scope
    keyword_matches = sum(1 for kw in epic_keywords if re.search(kw, text_lower))
    if keyword_matches >= 2:
        return True

    # Long text with "and" suggests multiple concerns
    return len(text) > 200 and text_lower.count(" and ") >= 2


def extract_epic_title(text: str) -> str:
    """Extract a concise title for an epic from the full text."""
    # Take first sentence or first 100 chars
    first_sentence = text.split(".")[0].strip()
    if len(first_sentence) <= 100:
        return first_sentence

    # Fall back to first 100 chars at word boundary
    truncated = text[:100]
    last_space = truncated.rfind(" ")
    if last_space > 50:
        return truncated[:last_space].strip()

    return truncated.strip()


def parse_user_input(text: str) -> ParsedInput:
    """Parse user input into task candidates.

    This is a heuristic parser that extracts actionable items from natural
    language input. It does NOT use an LLM - all parsing is deterministic.
    """
    text = text.strip()
    if not text:
        return ParsedInput(original_text=text)

    # Split into segments
    segments = split_into_segments(text)

    # Process each segment
    candidates: list[TaskCandidate] = []
    for i, segment in enumerate(segments):
        action_type, confidence = detect_action_type(segment)
        target = extract_target(segment, action_type)
        order_hint = detect_order_hint(segment)

        # Adjust order hint based on position in input
        order_hint += i * 10  # Natural ordering from input

        candidate = TaskCandidate(
            raw_text=segment,
            action_type=action_type,
            target=target,
            order_hint=order_hint,
            confidence=confidence,
        )
        candidates.append(candidate)

    # Sort by order hint
    candidates.sort(key=lambda c: c.order_hint)

    # Determine if this is an epic
    is_epic = is_likely_epic(text, len(candidates))
    epic_title = extract_epic_title(text) if is_epic else ""

    return ParsedInput(
        original_text=text,
        candidates=candidates,
        is_epic=is_epic,
        suggested_epic_title=epic_title,
    )
