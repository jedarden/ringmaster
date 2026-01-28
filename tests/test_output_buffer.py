"""Tests for output buffer overflow logging functionality."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from ringmaster.worker.output_buffer import OutputLine, WorkerOutputBuffer


class TestWorkerOutputBuffer:
    """Tests for WorkerOutputBuffer functionality."""

    async def test_basic_write_and_read(self):
        """Test basic write and read functionality works."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Write a line
        await buffer.write("worker-1", "Hello world")

        # Read it back
        lines = await buffer.get_recent("worker-1")
        assert len(lines) == 1
        assert lines[0].line == "Hello world"
        assert lines[0].line_number == 1

    async def test_subscriber_overflow_logging(self):
        """Test that overflow warnings are logged when subscriber queue is full."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Subscribe to worker output
        queue = await buffer.subscribe("worker-1", "sub-1")

        # Fill up the queue (maxsize=100 by default)
        # Put 100 items to fill it up
        for i in range(100):
            queue.put_nowait(OutputLine(f"line-{i}", line_number=i))

        # Now the queue should be full
        assert queue.qsize() == 100
        assert queue.full()

        # Mock the logger to capture log calls
        with patch('ringmaster.worker.output_buffer.logger') as mock_logger:
            # Write a line that should trigger overflow handling
            await buffer.write("worker-1", "This will trigger overflow")

            # Verify warning was logged
            mock_logger.warning.assert_called_once_with(
                "Output buffer queue full for worker worker-1, dropping oldest line"
            )

    async def test_overflow_warning_rate_limiting(self):
        """Test that overflow warnings are only logged once until queue is no longer full."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Subscribe to worker output
        queue = await buffer.subscribe("worker-1", "sub-1")

        # Fill up the queue
        for i in range(100):
            queue.put_nowait(OutputLine(f"line-{i}", line_number=i))

        with patch('ringmaster.worker.output_buffer.logger') as mock_logger:
            # Write multiple lines - should only log warning once
            await buffer.write("worker-1", "First overflow line")
            await buffer.write("worker-1", "Second overflow line")
            await buffer.write("worker-1", "Third overflow line")

            # Should only have been called once
            assert mock_logger.warning.call_count == 1
            mock_logger.warning.assert_called_with(
                "Output buffer queue full for worker worker-1, dropping oldest line"
            )

    async def test_overflow_warning_resets_after_queue_not_full(self):
        """Test that overflow warning flag resets when queue is no longer full."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Subscribe to worker output
        queue = await buffer.subscribe("worker-1", "sub-1")

        # Fill up the queue
        for i in range(100):
            queue.put_nowait(OutputLine(f"line-{i}", line_number=i))

        with patch('ringmaster.worker.output_buffer.logger') as mock_logger:
            # First overflow should log warning
            await buffer.write("worker-1", "First overflow line")
            assert mock_logger.warning.call_count == 1

            # Empty the entire queue
            while not queue.empty():
                queue.get_nowait()

            # Write another line - should succeed without overflow
            await buffer.write("worker-1", "Non-overflow line")

            # Now fill up again and write - should log warning again
            # Account for the one item that was just added
            for i in range(99):  # 99 + 1 already added = 100
                queue.put_nowait(OutputLine(f"refill-{i}", line_number=i))

            await buffer.write("worker-1", "Second overflow line")

            # Should have been called twice total now
            assert mock_logger.warning.call_count == 2

    async def test_multiple_workers_overflow_independently(self):
        """Test that overflow warnings are tracked per worker."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Subscribe to two different workers
        queue1 = await buffer.subscribe("worker-1", "sub-1")
        queue2 = await buffer.subscribe("worker-2", "sub-2")

        # Fill up only worker-1's queue
        for i in range(100):
            queue1.put_nowait(OutputLine(f"line-{i}", line_number=i))

        with patch('ringmaster.worker.output_buffer.logger') as mock_logger:
            # Worker-1 overflow should trigger warning
            await buffer.write("worker-1", "Worker 1 overflow")
            assert mock_logger.warning.call_count == 1

            # Worker-2 should not trigger warning (queue not full)
            await buffer.write("worker-2", "Worker 2 normal line")
            assert mock_logger.warning.call_count == 1  # Still just 1

            # Fill worker-2's queue (accounting for the one item already added)
            for i in range(99):  # 99 + 1 already added = 100
                queue2.put_nowait(OutputLine(f"line-{i}", line_number=i))

            await buffer.write("worker-2", "Worker 2 overflow")
            assert mock_logger.warning.call_count == 2  # Now 2

    async def test_no_overflow_when_no_subscribers(self):
        """Test that no overflow warnings occur when there are no subscribers."""
        buffer = WorkerOutputBuffer(max_lines=10)

        with patch('ringmaster.worker.output_buffer.logger') as mock_logger:
            # Write lines without any subscribers - should not trigger any overflow handling
            await buffer.write("worker-1", "Line 1")
            await buffer.write("worker-1", "Line 2")

            # No warnings should be logged
            mock_logger.warning.assert_not_called()

    async def test_overflow_tracking_initialized_for_new_workers(self):
        """Test that overflow tracking is properly initialized for new workers."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Write to a new worker should initialize overflow tracking
        await buffer.write("new-worker", "First line")

        # Check that overflow tracking was initialized
        assert "new-worker" in buffer._overflow_warnings
        assert buffer._overflow_warnings["new-worker"] is False

    async def test_get_buffer_stats_return_type(self):
        """Test that get_buffer_stats returns dict[str, dict[str, int]] as type hinted."""
        buffer = WorkerOutputBuffer(max_lines=10)

        # Test with empty buffer
        stats = buffer.get_buffer_stats()
        assert isinstance(stats, dict)
        assert stats == {}

        # Add some data for multiple workers
        await buffer.write("worker-1", "Line 1")
        await buffer.write("worker-1", "Line 2")
        await buffer.write("worker-2", "Line A")

        # Subscribe to one worker
        await buffer.subscribe("worker-1", "sub-1")

        # Get stats and verify structure and types
        stats = buffer.get_buffer_stats()
        assert isinstance(stats, dict)
        assert len(stats) == 2

        # Check worker-1 stats
        worker1_stats = stats["worker-1"]
        assert isinstance(worker1_stats, dict)
        assert len(worker1_stats) == 4

        # Verify all values are integers as type hinted
        assert isinstance(worker1_stats["line_count"], int)
        assert isinstance(worker1_stats["max_lines"], int)
        assert isinstance(worker1_stats["total_lines"], int)
        assert isinstance(worker1_stats["subscriber_count"], int)

        # Verify actual values
        assert worker1_stats["line_count"] == 2
        assert worker1_stats["max_lines"] == 10
        assert worker1_stats["total_lines"] == 2
        assert worker1_stats["subscriber_count"] == 1

        # Check worker-2 stats
        worker2_stats = stats["worker-2"]
        assert isinstance(worker2_stats, dict)
        assert len(worker2_stats) == 4

        # Verify all values are integers as type hinted
        assert isinstance(worker2_stats["line_count"], int)
        assert isinstance(worker2_stats["max_lines"], int)
        assert isinstance(worker2_stats["total_lines"], int)
        assert isinstance(worker2_stats["subscriber_count"], int)

        # Verify actual values
        assert worker2_stats["line_count"] == 1
        assert worker2_stats["max_lines"] == 10
        assert worker2_stats["total_lines"] == 1
        assert worker2_stats["subscriber_count"] == 0