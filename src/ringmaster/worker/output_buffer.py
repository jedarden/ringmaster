"""Output buffer for real-time worker output streaming."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class OutputLine:
    """A single line of output from a worker."""

    line: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    line_number: int = 0


class WorkerOutputBuffer:
    """Buffer for collecting and streaming worker output.

    Maintains a rolling buffer of output lines per worker.
    Supports multiple subscribers for real-time streaming.
    """

    def __init__(self, max_lines: int = 1000):
        """Initialize the output buffer.

        Args:
            max_lines: Maximum lines to retain per worker.
        """
        self.max_lines = max_lines
        self._buffers: dict[str, deque[OutputLine]] = {}
        self._line_counters: dict[str, int] = {}
        self._subscribers: dict[str, dict[str, asyncio.Queue]] = {}  # worker_id -> {sub_id: queue}
        self._overflow_warnings: dict[str, bool] = {}  # worker_id -> has_logged_overflow
        self._lock = asyncio.Lock()

    async def write(self, worker_id: str, line: str) -> None:
        """Write a line of output for a worker.

        Args:
            worker_id: The worker ID.
            line: The output line.
        """
        async with self._lock:
            # Initialize buffer if needed
            if worker_id not in self._buffers:
                self._buffers[worker_id] = deque(maxlen=self.max_lines)
                self._line_counters[worker_id] = 0
                self._overflow_warnings[worker_id] = False

            # Create output line
            self._line_counters[worker_id] += 1
            output_line = OutputLine(
                line=line,
                line_number=self._line_counters[worker_id],
            )

            # Add to buffer
            self._buffers[worker_id].append(output_line)

            # Notify subscribers
            if worker_id in self._subscribers:
                for queue in self._subscribers[worker_id].values():
                    try:
                        queue.put_nowait(output_line)
                        # Reset overflow warning flag on successful put
                        if self._overflow_warnings.get(worker_id, False):
                            self._overflow_warnings[worker_id] = False
                    except asyncio.QueueFull:
                        # Log warning only once when overflow starts
                        if not self._overflow_warnings.get(worker_id, False):
                            logger.warning(f"Output buffer queue full for worker {worker_id}, dropping oldest line")
                            self._overflow_warnings[worker_id] = True

                        # Drop oldest if queue is full
                        try:
                            queue.get_nowait()
                            queue.put_nowait(output_line)
                        except asyncio.QueueEmpty:
                            pass

    async def get_recent(
        self, worker_id: str, limit: int = 100, since_line: int = 0
    ) -> list[OutputLine]:
        """Get recent output lines for a worker.

        Args:
            worker_id: The worker ID.
            limit: Maximum number of lines to return.
            since_line: Only return lines after this line number.

        Returns:
            List of output lines.
        """
        async with self._lock:
            if worker_id not in self._buffers:
                return []

            lines = list(self._buffers[worker_id])

            # Filter by line number
            if since_line > 0:
                lines = [ln for ln in lines if ln.line_number > since_line]

            # Apply limit
            return lines[-limit:]

    async def subscribe(self, worker_id: str, subscriber_id: str) -> asyncio.Queue:
        """Subscribe to output for a worker.

        Args:
            worker_id: The worker ID to subscribe to.
            subscriber_id: Unique ID for the subscriber.

        Returns:
            Queue that will receive output lines.
        """
        async with self._lock:
            if worker_id not in self._subscribers:
                self._subscribers[worker_id] = {}

            queue: asyncio.Queue = asyncio.Queue(maxsize=100)
            self._subscribers[worker_id][subscriber_id] = queue
            return queue

    async def unsubscribe(self, worker_id: str, subscriber_id: str) -> None:
        """Unsubscribe from output for a worker.

        Args:
            worker_id: The worker ID.
            subscriber_id: The subscriber ID.
        """
        async with self._lock:
            if worker_id in self._subscribers:
                self._subscribers[worker_id].pop(subscriber_id, None)
                if not self._subscribers[worker_id]:
                    del self._subscribers[worker_id]

    async def clear(self, worker_id: str) -> None:
        """Clear output buffer for a worker.

        Args:
            worker_id: The worker ID.
        """
        async with self._lock:
            if worker_id in self._buffers:
                self._buffers[worker_id].clear()
                self._line_counters[worker_id] = 0

    def get_buffer_stats(self) -> dict[str, dict]:
        """Get statistics about current buffers.

        Returns:
            Dict of worker_id -> stats.
        """
        stats = {}
        for worker_id, buffer in self._buffers.items():
            stats[worker_id] = {
                "line_count": len(buffer),
                "max_lines": self.max_lines,
                "total_lines": self._line_counters.get(worker_id, 0),
                "subscriber_count": len(self._subscribers.get(worker_id, {})),
            }
        return stats


# Global output buffer instance
output_buffer = WorkerOutputBuffer()

__all__ = ["OutputLine", "WorkerOutputBuffer", "output_buffer"]
