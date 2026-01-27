"""Worker monitoring for long-running task detection.

Based on docs/09-remaining-decisions.md Section 10:
- Heartbeat-based liveness detection
- Context degradation detection
- No hard timeouts - intelligent monitoring

Research sources:
- Anthropic's guidance on effective harnesses for long-running agents
- Cursor's learnings on agent scaling
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum


class LivenessStatus(Enum):
    """Worker liveness states based on output activity."""

    ACTIVE = "active"  # Producing output normally
    THINKING = "thinking"  # Brief pause (< 2 min), normal
    SLOW = "slow"  # Extended pause (2-10 min), may be working on complex task
    LIKELY_HUNG = "likely_hung"  # No output for > 10 min, probably stuck
    DEGRADED = "degraded"  # Context degradation detected


@dataclass
class DegradationSignals:
    """Signals indicating potential context degradation.

    Context degradation occurs when an LLM agent:
    - Starts repeating itself
    - Forgets previous constraints
    - Shows signs of circular reasoning
    """

    repetition_score: float = 0.0  # 0-1, higher = more repetition
    apology_count: int = 0  # "I apologize", "Sorry"
    retry_count: int = 0  # "I already tried", "Let me try again"
    contradiction_count: int = 0  # Conflicting statements detected
    is_degraded: bool = False


@dataclass
class MonitorState:
    """Current monitoring state for a worker."""

    worker_id: str
    task_id: str | None = None
    last_output_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_output_size: int = 0
    output_lines: list[str] = field(default_factory=list)
    liveness_status: LivenessStatus = LivenessStatus.ACTIVE
    degradation: DegradationSignals = field(default_factory=DegradationSignals)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Configurable thresholds
    thinking_threshold_minutes: float = 2.0
    slow_threshold_minutes: float = 10.0
    hung_threshold_minutes: float = 20.0


class WorkerMonitor:
    """Monitor for detecting long-running and degraded workers.

    Tracks heartbeats (output activity) and analyzes output for:
    - Liveness: Is the worker still producing output?
    - Degradation: Is the worker showing signs of context drift?

    Usage:
        monitor = WorkerMonitor(worker_id="claude-1", task_id="task-123")

        # Feed output lines as they arrive
        await monitor.record_output("Writing tests for auth module...")

        # Check status periodically
        status = monitor.check_liveness()
        if status == LivenessStatus.LIKELY_HUNG:
            # Take recovery action

        # Check for degradation
        degradation = monitor.check_degradation()
        if degradation.is_degraded:
            # Consider restarting with fresh context
    """

    # Patterns indicating context degradation
    APOLOGY_PATTERNS = [
        r"\bi apologize\b",
        r"\bsorry\b",
        r"\bmy mistake\b",
        r"\bi was wrong\b",
    ]

    RETRY_PATTERNS = [
        r"\bi already tried\b",
        r"\blet me try again\b",
        r"\bpreviously attempted\b",
        r"\bone more time\b",
        r"\btrying again\b",
    ]

    CONSTRAINT_VIOLATION_PATTERNS = [
        r"\bignoring the constraint\b",
        r"\bdespite the requirement\b",
        r"\beven though .+ said\b",
    ]

    def __init__(
        self,
        worker_id: str,
        task_id: str | None = None,
        max_output_history: int = 500,
        repetition_threshold: float = 0.3,
    ):
        """Initialize the monitor.

        Args:
            worker_id: The worker being monitored.
            task_id: The task being executed (if any).
            max_output_history: Maximum output lines to keep for analysis.
            repetition_threshold: Score above which degradation is detected.
        """
        self.state = MonitorState(worker_id=worker_id, task_id=task_id)
        self.max_output_history = max_output_history
        self.repetition_threshold = repetition_threshold
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[str, list[re.Pattern]]:
        """Compile regex patterns for efficiency."""
        return {
            "apology": [re.compile(p, re.IGNORECASE) for p in self.APOLOGY_PATTERNS],
            "retry": [re.compile(p, re.IGNORECASE) for p in self.RETRY_PATTERNS],
            "constraint": [
                re.compile(p, re.IGNORECASE) for p in self.CONSTRAINT_VIOLATION_PATTERNS
            ],
        }

    async def record_output(self, line: str) -> None:
        """Record a line of output from the worker.

        Updates heartbeat timestamp and stores output for analysis.

        Args:
            line: A line of worker output.
        """
        self.state.last_output_time = datetime.now(UTC)
        self.state.last_output_size += len(line)

        # Store for degradation analysis
        self.state.output_lines.append(line)

        # Trim history if too long
        if len(self.state.output_lines) > self.max_output_history:
            self.state.output_lines = self.state.output_lines[-self.max_output_history :]

        # Update liveness to active since we got output
        self.state.liveness_status = LivenessStatus.ACTIVE

    def check_liveness(self) -> LivenessStatus:
        """Check worker liveness based on output activity.

        Returns:
            Current liveness status.
        """
        now = datetime.now(UTC)
        idle_time = now - self.state.last_output_time
        idle_minutes = idle_time.total_seconds() / 60

        if idle_minutes < self.state.thinking_threshold_minutes:
            status = LivenessStatus.ACTIVE
        elif idle_minutes < self.state.slow_threshold_minutes:
            status = LivenessStatus.THINKING
        elif idle_minutes < self.state.hung_threshold_minutes:
            status = LivenessStatus.SLOW
        else:
            status = LivenessStatus.LIKELY_HUNG

        self.state.liveness_status = status
        return status

    def check_degradation(self) -> DegradationSignals:
        """Analyze output for signs of context degradation.

        Checks for:
        - Repetition: Same phrases/lines appearing multiple times
        - Apologies: Excessive "I apologize", "Sorry"
        - Retries: "I already tried", "Let me try again"
        - Contradictions: Conflicting statements

        Returns:
            DegradationSignals with analysis results.
        """
        signals = DegradationSignals()

        if not self.state.output_lines:
            self.state.degradation = signals
            return signals

        # Analyze recent output
        recent = self.state.output_lines[-100:]  # Last 100 lines
        text = "\n".join(recent).lower()

        # Count pattern matches
        for pattern in self._compiled_patterns["apology"]:
            signals.apology_count += len(pattern.findall(text))

        for pattern in self._compiled_patterns["retry"]:
            signals.retry_count += len(pattern.findall(text))

        for pattern in self._compiled_patterns["constraint"]:
            signals.contradiction_count += len(pattern.findall(text))

        # Calculate repetition score
        signals.repetition_score = self._calculate_repetition_score(recent)

        # Determine if degraded based on signals
        signals.is_degraded = (
            signals.repetition_score >= self.repetition_threshold
            or signals.apology_count >= 5
            or signals.retry_count >= 3
            or signals.contradiction_count >= 2
        )

        if signals.is_degraded:
            self.state.liveness_status = LivenessStatus.DEGRADED

        self.state.degradation = signals
        return signals

    def _calculate_repetition_score(self, lines: list[str]) -> float:
        """Calculate how repetitive the output is.

        Uses n-gram analysis to detect repeated phrases.

        Args:
            lines: Lines of output to analyze.

        Returns:
            Score from 0-1, higher means more repetition.
        """
        if len(lines) < 10:
            return 0.0

        # Normalize lines for comparison
        normalized = [line.strip().lower() for line in lines if line.strip()]

        if not normalized:
            return 0.0

        # Count exact line repetitions
        line_counts = Counter(normalized)
        repeated_lines = sum(1 for count in line_counts.values() if count > 1)
        line_repetition = repeated_lines / len(line_counts) if line_counts else 0

        # Count 3-gram repetitions (consecutive words)
        all_text = " ".join(normalized)
        words = all_text.split()

        if len(words) < 6:
            return line_repetition

        ngrams = []
        for i in range(len(words) - 2):
            ngrams.append(tuple(words[i : i + 3]))

        ngram_counts = Counter(ngrams)
        repeated_ngrams = sum(1 for count in ngram_counts.values() if count > 2)
        ngram_repetition = repeated_ngrams / len(ngram_counts) if ngram_counts else 0

        # Combine scores with weights
        return 0.6 * line_repetition + 0.4 * ngram_repetition

    def get_runtime(self) -> timedelta:
        """Get total runtime since monitoring started."""
        return datetime.now(UTC) - self.state.started_at

    def get_idle_time(self) -> timedelta:
        """Get time since last output."""
        return datetime.now(UTC) - self.state.last_output_time

    def reset(self, task_id: str | None = None) -> None:
        """Reset monitor state for a new task.

        Args:
            task_id: New task ID (optional).
        """
        now = datetime.now(UTC)
        self.state = MonitorState(
            worker_id=self.state.worker_id,
            task_id=task_id,
            last_output_time=now,
            started_at=now,
        )


@dataclass
class RecoveryAction:
    """Recommended recovery action based on monitoring."""

    action: str  # "none", "log_warning", "interrupt", "checkpoint_restart", "escalate"
    reason: str
    urgency: str  # "low", "medium", "high", "critical"


def recommend_recovery(monitor: WorkerMonitor) -> RecoveryAction:
    """Recommend a recovery action based on monitor state.

    Decision logic:
    - ACTIVE: No action needed
    - THINKING: No action needed (normal)
    - SLOW: Log warning, may be complex task
    - LIKELY_HUNG: Interrupt and restart
    - DEGRADED: Checkpoint and restart with fresh context

    Args:
        monitor: The WorkerMonitor to analyze.

    Returns:
        Recommended RecoveryAction.
    """
    liveness = monitor.check_liveness()
    degradation = monitor.check_degradation()

    if degradation.is_degraded:
        return RecoveryAction(
            action="checkpoint_restart",
            reason=(
                f"Context degradation detected: "
                f"repetition={degradation.repetition_score:.2f}, "
                f"apologies={degradation.apology_count}, "
                f"retries={degradation.retry_count}"
            ),
            urgency="high",
        )

    if liveness == LivenessStatus.ACTIVE:
        return RecoveryAction(
            action="none",
            reason="Worker is active",
            urgency="low",
        )

    if liveness == LivenessStatus.THINKING:
        return RecoveryAction(
            action="none",
            reason="Worker is thinking (brief pause)",
            urgency="low",
        )

    if liveness == LivenessStatus.SLOW:
        idle_minutes = monitor.get_idle_time().total_seconds() / 60
        return RecoveryAction(
            action="log_warning",
            reason=f"Worker slow (idle {idle_minutes:.1f} min), may be working on complex task",
            urgency="medium",
        )

    if liveness == LivenessStatus.LIKELY_HUNG:
        idle_minutes = monitor.get_idle_time().total_seconds() / 60
        return RecoveryAction(
            action="interrupt",
            reason=f"Worker likely hung (idle {idle_minutes:.1f} min)",
            urgency="high",
        )

    return RecoveryAction(
        action="escalate",
        reason=f"Unknown state: {liveness}",
        urgency="critical",
    )
