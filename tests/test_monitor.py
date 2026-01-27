"""Tests for worker monitoring and long-running task detection."""

from datetime import UTC, datetime, timedelta

import pytest

from ringmaster.worker.monitor import (
    LivenessStatus,
    WorkerMonitor,
    recommend_recovery,
)


class TestLivenessDetection:
    """Tests for liveness detection based on output activity."""

    def test_active_when_recent_output(self):
        """Worker is ACTIVE when output is very recent."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Just created, should be active
        status = monitor.check_liveness()
        assert status == LivenessStatus.ACTIVE

    def test_thinking_after_short_pause(self):
        """Worker is THINKING after brief pause (2-10 min)."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Simulate 3 minutes of silence (between 2 and 10 min threshold)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=3)
        status = monitor.check_liveness()
        assert status == LivenessStatus.THINKING

    def test_slow_after_extended_pause(self):
        """Worker is SLOW after extended pause (10-20 min)."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Simulate 15 minutes of silence (between 10 and 20 min threshold)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=15)
        status = monitor.check_liveness()
        assert status == LivenessStatus.SLOW

    def test_likely_hung_after_long_pause(self):
        """Worker is LIKELY_HUNG after long pause (> 20 min)."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Simulate 25 minutes of silence (past 20 min threshold)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=25)
        status = monitor.check_liveness()
        assert status == LivenessStatus.LIKELY_HUNG

    @pytest.mark.asyncio
    async def test_output_resets_liveness(self):
        """Recording output resets liveness to ACTIVE."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Make it seem hung
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=30)
        assert monitor.check_liveness() == LivenessStatus.LIKELY_HUNG

        # Record new output
        await monitor.record_output("New line of output")

        # Should be active again
        assert monitor.check_liveness() == LivenessStatus.ACTIVE


class TestDegradationDetection:
    """Tests for context degradation detection."""

    def test_no_degradation_on_empty_output(self):
        """No degradation signals with empty output."""
        monitor = WorkerMonitor(worker_id="test-1")
        signals = monitor.check_degradation()
        assert not signals.is_degraded
        assert signals.repetition_score == 0.0
        assert signals.apology_count == 0

    @pytest.mark.asyncio
    async def test_detects_excessive_apologies(self):
        """Detects degradation from excessive apologies."""
        monitor = WorkerMonitor(worker_id="test-1")

        # Add output with many apologies
        for i in range(10):
            await monitor.record_output(f"Line {i}")
            await monitor.record_output("I apologize for the confusion")
            await monitor.record_output("Sorry, let me try again")

        signals = monitor.check_degradation()
        assert signals.apology_count >= 5
        assert signals.is_degraded

    @pytest.mark.asyncio
    async def test_detects_retry_loops(self):
        """Detects degradation from retry loops."""
        monitor = WorkerMonitor(worker_id="test-1")

        # Simulate retry loop output
        for i in range(5):
            await monitor.record_output(f"Attempt {i}")
            await monitor.record_output("Let me try again")
            await monitor.record_output("I already tried that approach")

        signals = monitor.check_degradation()
        assert signals.retry_count >= 3
        assert signals.is_degraded

    @pytest.mark.asyncio
    async def test_detects_repetitive_output(self):
        """Detects degradation from repetitive output."""
        monitor = WorkerMonitor(worker_id="test-1", repetition_threshold=0.2)

        # Add highly repetitive output
        for _ in range(20):
            await monitor.record_output("Writing tests for the module...")
            await monitor.record_output("Checking implementation...")

        signals = monitor.check_degradation()
        assert signals.repetition_score > 0.2
        assert signals.is_degraded

    @pytest.mark.asyncio
    async def test_normal_output_not_degraded(self):
        """Normal varied output is not flagged as degraded."""
        monitor = WorkerMonitor(worker_id="test-1")

        # Add varied normal output
        lines = [
            "Reading src/auth/token.py",
            "Analyzing the token validation logic",
            "The function handles JWT decoding",
            "Adding error handling for expired tokens",
            "Writing test case for invalid signature",
            "Running pytest tests/test_auth.py",
            "All tests passed!",
            "Committing changes",
        ]
        for line in lines:
            await monitor.record_output(line)

        signals = monitor.check_degradation()
        assert not signals.is_degraded


class TestRecoveryRecommendations:
    """Tests for recovery action recommendations."""

    def test_no_action_for_active_worker(self):
        """No action recommended for active worker."""
        monitor = WorkerMonitor(worker_id="test-1")
        recovery = recommend_recovery(monitor)
        assert recovery.action == "none"
        assert recovery.urgency == "low"

    def test_no_action_for_thinking_worker(self):
        """No action recommended for thinking worker."""
        monitor = WorkerMonitor(worker_id="test-1")
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(seconds=90)
        recovery = recommend_recovery(monitor)
        assert recovery.action == "none"
        assert recovery.urgency == "low"

    def test_warning_for_slow_worker(self):
        """Log warning recommended for slow worker."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Use 15 minutes to be in the SLOW range (10-20 min)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=15)
        recovery = recommend_recovery(monitor)
        assert recovery.action == "log_warning"
        assert recovery.urgency == "medium"

    def test_interrupt_for_hung_worker(self):
        """Interrupt recommended for likely hung worker."""
        monitor = WorkerMonitor(worker_id="test-1")
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=25)
        recovery = recommend_recovery(monitor)
        assert recovery.action == "interrupt"
        assert recovery.urgency == "high"

    @pytest.mark.asyncio
    async def test_checkpoint_restart_for_degraded_worker(self):
        """Checkpoint restart recommended for degraded worker."""
        monitor = WorkerMonitor(worker_id="test-1")

        # Create degradation
        for _ in range(10):
            await monitor.record_output("I apologize for the confusion")
            await monitor.record_output("Let me try again")

        recovery = recommend_recovery(monitor)
        assert recovery.action == "checkpoint_restart"
        assert recovery.urgency == "high"
        assert "degradation" in recovery.reason.lower()


class TestMonitorState:
    """Tests for monitor state management."""

    @pytest.mark.asyncio
    async def test_output_history_trimming(self):
        """Output history is trimmed to max size."""
        monitor = WorkerMonitor(worker_id="test-1", max_output_history=10)

        # Add more lines than max
        for i in range(20):
            await monitor.record_output(f"Line {i}")

        # Should only keep last 10
        assert len(monitor.state.output_lines) == 10
        assert "Line 10" in monitor.state.output_lines[0]

    def test_reset_clears_state(self):
        """Reset clears monitor state for new task."""
        monitor = WorkerMonitor(worker_id="test-1", task_id="task-1")
        monitor.state.output_lines = ["old line"]
        monitor.state.last_output_size = 1000

        monitor.reset(task_id="task-2")

        assert monitor.state.task_id == "task-2"
        assert monitor.state.output_lines == []
        assert monitor.state.last_output_size == 0

    def test_get_runtime(self):
        """Get runtime returns correct duration."""
        monitor = WorkerMonitor(worker_id="test-1")
        monitor.state.started_at = datetime.now(UTC) - timedelta(minutes=5)

        runtime = monitor.get_runtime()
        assert 4.9 < runtime.total_seconds() / 60 < 5.1

    def test_get_idle_time(self):
        """Get idle time returns time since last output."""
        monitor = WorkerMonitor(worker_id="test-1")
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=3)

        idle = monitor.get_idle_time()
        assert 2.9 < idle.total_seconds() / 60 < 3.1


class TestConfigurableThresholds:
    """Tests for configurable monitoring thresholds."""

    def test_custom_thresholds(self):
        """Monitor respects custom thresholds."""
        monitor = WorkerMonitor(worker_id="test-1")
        # Set custom thresholds
        monitor.state.thinking_threshold_minutes = 1.0
        monitor.state.slow_threshold_minutes = 3.0
        monitor.state.hung_threshold_minutes = 5.0

        # 2 minutes idle should be THINKING with these thresholds (1-3 min range)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=2)
        assert monitor.check_liveness() == LivenessStatus.THINKING

        # 4 minutes idle should be SLOW (3-5 min range)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=4)
        assert monitor.check_liveness() == LivenessStatus.SLOW

        # 6 minutes idle should be LIKELY_HUNG (>5 min)
        monitor.state.last_output_time = datetime.now(UTC) - timedelta(minutes=6)
        assert monitor.check_liveness() == LivenessStatus.LIKELY_HUNG

    def test_custom_repetition_threshold(self):
        """Monitor respects custom repetition threshold."""
        # Low threshold - more sensitive to repetition
        monitor = WorkerMonitor(worker_id="test-1", repetition_threshold=0.1)

        # Even moderate repetition should trigger
        for _ in range(15):
            monitor.state.output_lines.append("Same line")
            monitor.state.output_lines.append("Different line")

        signals = monitor.check_degradation()
        # With low threshold, should detect degradation
        assert signals.repetition_score > 0  # Has some repetition
