"""Worker output parsing for multi-signal outcome detection.

Based on docs/09-remaining-decisions.md Section 6:
- Multi-signal approach: exit codes + structured markers + verification commands
- SUCCESS_MARKERS, FAILURE_MARKERS, DECISION_MARKERS
- Test pass/fail detection
"""

import re
from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    """Detected outcome from worker output."""

    SUCCESS = "success"  # Clear success signals
    LIKELY_SUCCESS = "likely_success"  # Exit code 0 but no explicit markers
    FAILED = "failed"  # Clear failure signals
    LIKELY_FAILED = "likely_failed"  # Exit code != 0 but no explicit markers
    NEEDS_DECISION = "needs_decision"  # Worker needs human input
    UNKNOWN = "unknown"  # Unable to determine


@dataclass
class OutcomeSignals:
    """Signals detected in worker output."""

    exit_code_success: bool
    has_success_marker: bool
    has_failure_marker: bool
    has_decision_marker: bool
    tests_passed: bool
    tests_failed: bool
    has_completion_signal: bool

    @property
    def summary(self) -> dict[str, bool]:
        """Return signals as a dict for logging."""
        return {
            "exit_code_success": self.exit_code_success,
            "has_success_marker": self.has_success_marker,
            "has_failure_marker": self.has_failure_marker,
            "has_decision_marker": self.has_decision_marker,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "has_completion_signal": self.has_completion_signal,
        }


@dataclass
class OutcomeResult:
    """Result of outcome detection."""

    outcome: Outcome
    signals: OutcomeSignals
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable explanation
    decision_question: str | None = None  # If NEEDS_DECISION, the question

    @property
    def is_success(self) -> bool:
        """Check if outcome indicates success."""
        return self.outcome in (Outcome.SUCCESS, Outcome.LIKELY_SUCCESS)

    @property
    def is_failure(self) -> bool:
        """Check if outcome indicates failure."""
        return self.outcome in (Outcome.FAILED, Outcome.LIKELY_FAILED)

    @property
    def needs_human_input(self) -> bool:
        """Check if worker needs human decision."""
        return self.outcome == Outcome.NEEDS_DECISION


# Success markers - indicate explicit task completion
SUCCESS_MARKERS = [
    "✓ Task complete",
    "✓ All tests passing",
    "✓ Build successful",
    "Successfully completed",
    "<promise>COMPLETE</promise>",
    "DONE",
    "Task completed successfully",
    "Changes committed",
    "All checks passed",
]

# Failure markers - indicate explicit task failure
FAILURE_MARKERS = [
    "✗ Failed",
    "✗ Tests failing",
    "Error:",
    "FAILED",
    "Unable to complete",
    "Build failed",
    "Tests failed",
    "Compilation error",
    "Fatal error",
    "Cannot continue",
]

# Decision markers - indicate need for human input
DECISION_MARKERS = [
    "? Need clarification",
    "? Decision needed",
    "? Multiple options",
    "BLOCKED:",
    "Need your input",
    "Which option",
    "Should I",
    "Do you want me to",
    "Please confirm",
    "Awaiting decision",
]

# Test result patterns
TEST_PASS_PATTERNS = [
    r"(\d+)\s*tests?\s*passed",
    r"✓\s*\d+\s*passing",
    r"OK\s*\(\d+\s*tests?\)",
    r"PASSED",
    r"All \d+ tests passed",
    r"\d+ passed",
]

TEST_FAIL_PATTERNS = [
    r"(\d+)\s*tests?\s*failed",
    r"✗\s*\d+\s*failing",
    r"FAILED\s*\(\d+\s*failures?\)",
    r"\d+ failed",
    r"Failures:\s*\d+",
    r"errors?:\s*\d+",
]


def detect_outcome(
    output: str,
    exit_code: int | None = None,
    completion_signal: str = "<promise>COMPLETE</promise>",
) -> OutcomeResult:
    """Detect task outcome using multiple signals.

    Args:
        output: The worker's complete output text.
        exit_code: Process exit code (None if not available).
        completion_signal: The expected completion signal.

    Returns:
        OutcomeResult with detected outcome and reasoning.
    """
    # Normalize output for searching
    output_lower = output.lower()

    # Detect signals
    signals = OutcomeSignals(
        exit_code_success=exit_code == 0 if exit_code is not None else False,
        has_success_marker=_has_any_marker(output, SUCCESS_MARKERS),
        has_failure_marker=_has_any_marker(output, FAILURE_MARKERS),
        has_decision_marker=_has_any_marker(output, DECISION_MARKERS),
        tests_passed=_matches_any_pattern(output_lower, TEST_PASS_PATTERNS),
        tests_failed=_matches_any_pattern(output_lower, TEST_FAIL_PATTERNS),
        has_completion_signal=completion_signal in output,
    )

    # Determine outcome based on signal priority
    decision_question = None

    # Priority 1: Decision needed takes precedence
    if signals.has_decision_marker:
        decision_question = _extract_decision_question(output)
        return OutcomeResult(
            outcome=Outcome.NEEDS_DECISION,
            signals=signals,
            confidence=0.9,
            reason="Worker needs human input/decision",
            decision_question=decision_question,
        )

    # Priority 2: Explicit failure markers
    if signals.has_failure_marker or signals.tests_failed:
        confidence = 0.95 if signals.has_failure_marker else 0.85
        reason = []
        if signals.has_failure_marker:
            reason.append("Explicit failure marker detected")
        if signals.tests_failed:
            reason.append("Test failures detected")
        return OutcomeResult(
            outcome=Outcome.FAILED,
            signals=signals,
            confidence=confidence,
            reason="; ".join(reason),
        )

    # Priority 3: Completion signal or explicit success markers + good exit code
    if signals.has_completion_signal:
        return OutcomeResult(
            outcome=Outcome.SUCCESS,
            signals=signals,
            confidence=0.95,
            reason="Completion signal detected",
        )

    if signals.has_success_marker and signals.exit_code_success:
        return OutcomeResult(
            outcome=Outcome.SUCCESS,
            signals=signals,
            confidence=0.9,
            reason="Success marker and exit code 0",
        )

    # Priority 4: Tests passed is a strong signal
    if signals.tests_passed and not signals.tests_failed:
        confidence = 0.85 if signals.exit_code_success else 0.7
        return OutcomeResult(
            outcome=Outcome.SUCCESS if signals.exit_code_success else Outcome.LIKELY_SUCCESS,
            signals=signals,
            confidence=confidence,
            reason="Tests passed",
        )

    # Priority 5: Exit code alone (weak signal, but fallback)
    if exit_code is not None:
        if exit_code == 0:
            return OutcomeResult(
                outcome=Outcome.LIKELY_SUCCESS,
                signals=signals,
                confidence=0.6,
                reason="Exit code 0 (no explicit markers)",
            )
        else:
            return OutcomeResult(
                outcome=Outcome.LIKELY_FAILED,
                signals=signals,
                confidence=0.6,
                reason=f"Exit code {exit_code} (no explicit markers)",
            )

    # No signals available
    return OutcomeResult(
        outcome=Outcome.UNKNOWN,
        signals=signals,
        confidence=0.0,
        reason="Unable to determine outcome (no exit code or markers)",
    )


def _has_any_marker(text: str, markers: list[str]) -> bool:
    """Check if text contains any of the markers (case-insensitive for most)."""
    text_lower = text.lower()
    for marker in markers:
        # Some markers should be case-sensitive (like <promise>)
        if marker.startswith("<") or marker.isupper():
            if marker in text:
                return True
        elif marker.lower() in text_lower:
            return True
    return False


def _matches_any_pattern(text: str, patterns: list[str]) -> bool:
    """Check if text matches any regex pattern."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _extract_decision_question(output: str) -> str | None:
    """Extract the decision question from output.

    Looks for patterns like:
    - "? Decision needed: <question>"
    - "BLOCKED: <reason>"
    - "Should I <action>?"
    """
    # Try specific patterns first
    patterns = [
        r"\?\s*Decision needed:\s*([^\n]+)",
        r"\?\s*Need clarification:\s*([^\n]+)",
        r"BLOCKED:\s*([^\n]+)",
        r"Should I ([^?]+\?)",
        r"Do you want me to ([^?]+\?)",
        r"Please confirm[:\s]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fallback: look for question marks in recent lines
    lines = output.strip().split("\n")
    for line in reversed(lines[-20:]):  # Check last 20 lines
        if "?" in line and len(line) > 10:
            # Skip common non-question lines
            skip_patterns = ["tests?", "files?", "seconds?", "ms"]
            if not any(re.search(p, line, re.IGNORECASE) for p in skip_patterns):
                return line.strip()

    return None


def parse_test_results(output: str) -> dict[str, int | None]:
    """Parse test results from output.

    Returns:
        Dict with 'passed', 'failed', 'skipped' counts (None if not found).
    """
    results: dict[str, int | None] = {"passed": None, "failed": None, "skipped": None}
    output_lower = output.lower()

    # Look for passed count
    pass_patterns = [
        r"(\d+)\s*(?:tests?\s*)?passed",
        r"(\d+)\s*passing",
        r"OK\s*\((\d+)\s*tests?\)",
    ]
    for pattern in pass_patterns:
        match = re.search(pattern, output_lower)
        if match:
            results["passed"] = int(match.group(1))
            break

    # Look for failed count
    fail_patterns = [
        r"(\d+)\s*(?:tests?\s*)?failed",
        r"(\d+)\s*failing",
        r"failures?:\s*(\d+)",
    ]
    for pattern in fail_patterns:
        match = re.search(pattern, output_lower)
        if match:
            results["failed"] = int(match.group(1))
            break

    # Look for skipped count
    skip_patterns = [
        r"(\d+)\s*(?:tests?\s*)?skipped",
        r"(\d+)\s*pending",
    ]
    for pattern in skip_patterns:
        match = re.search(pattern, output_lower)
        if match:
            results["skipped"] = int(match.group(1))
            break

    return results
