"""Bead Creator service for parsing and decomposing user input into tasks.

The bead-creator transforms natural language input into structured work units:
- Parses input to extract actionable items
- Detects existing matches to update rather than duplicate
- Decomposes large inputs into smaller, atomic tasks
- Sets dependencies based on semantic ordering
"""

from ringmaster.creator.decomposer import (
    decompose_candidate,
    is_too_large,
)
from ringmaster.creator.matcher import (
    find_matching_task,
    similarity_score,
)
from ringmaster.creator.parser import (
    ParsedInput,
    TaskCandidate,
    parse_user_input,
)
from ringmaster.creator.service import (
    BeadCreator,
    CreationResult,
)

__all__ = [
    "BeadCreator",
    "CreationResult",
    "ParsedInput",
    "TaskCandidate",
    "parse_user_input",
    "decompose_candidate",
    "is_too_large",
    "find_matching_task",
    "similarity_score",
]
