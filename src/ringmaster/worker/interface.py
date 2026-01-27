"""Worker interface abstraction.

Based on docs/02-worker-interface.md:
- CLI-based worker abstraction
- Support for Claude Code, Aider, Codex, etc.
- Streaming output capture
- Session lifecycle management
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """Worker session status."""

    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SessionConfig:
    """Configuration for a worker session."""

    working_dir: Path
    prompt: str
    model: str | None = None
    timeout_seconds: int = 1800
    env_vars: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)
    completion_signal: str = "<promise>COMPLETE</promise>"


@dataclass
class SessionResult:
    """Result of a worker session."""

    status: SessionStatus
    output: str
    error: str | None = None
    exit_code: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0

    @property
    def duration_seconds(self) -> float | None:
        """Calculate session duration."""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    @property
    def success(self) -> bool:
        """Check if session completed successfully."""
        return self.status == SessionStatus.COMPLETED


class WorkerInterface(ABC):
    """Abstract interface for coding agent workers.

    Implementations provide platform-specific CLI invocation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Worker type name (e.g., 'claude-code', 'aider')."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the worker CLI is available."""
        ...

    @abstractmethod
    async def start_session(
        self,
        config: SessionConfig,
    ) -> "SessionHandle":
        """Start a new coding session.

        Args:
            config: Session configuration including prompt and working directory.

        Returns:
            SessionHandle for monitoring and controlling the session.
        """
        ...

    async def check_installation(self) -> tuple[bool, str]:
        """Check if the worker is properly installed.

        Returns:
            Tuple of (is_installed, message).
        """
        available = await self.is_available()
        if available:
            return True, f"{self.name} is available"
        return False, f"{self.name} not found. Please install it first."


class SessionHandle:
    """Handle for an active worker session."""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        config: SessionConfig,
        worker_name: str,
    ):
        self.process = process
        self.config = config
        self.worker_name = worker_name
        self.started_at = datetime.now(UTC)
        self._output_lines: list[str] = []
        self._error_lines: list[str] = []
        self._completed = False

    async def stream_output(self) -> AsyncIterator[str]:
        """Stream output lines from the worker."""
        if not self.process.stdout:
            return

        while True:
            try:
                line = await asyncio.wait_for(
                    self.process.stdout.readline(),
                    timeout=1.0,
                )
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                self._output_lines.append(decoded)
                yield decoded

                # Check for completion signal
                if self.config.completion_signal in decoded:
                    logger.info(f"Completion signal detected in {self.worker_name} output")

            except TimeoutError:
                # Check if process is still running
                if self.process.returncode is not None:
                    break
                continue

    async def wait(self, timeout: float | None = None) -> SessionResult:
        """Wait for the session to complete.

        Args:
            timeout: Maximum time to wait in seconds. None means use config timeout.

        Returns:
            SessionResult with outcome details.
        """
        timeout = timeout or self.config.timeout_seconds
        status = SessionStatus.RUNNING
        started_at = datetime.now(UTC)

        try:
            # Collect remaining output with overall timeout enforcement
            # We wrap the entire streaming+wait operation to enforce the timeout
            async def _collect_and_wait() -> None:
                # First, stream all available output
                async for _line in self.stream_output():
                    # Check if we've exceeded the timeout during streaming
                    elapsed = (datetime.now(UTC) - started_at).total_seconds()
                    if elapsed > timeout:
                        raise TimeoutError(f"Overall timeout of {timeout}s exceeded during streaming")
                    # Yield control to allow other tasks to run
                    await asyncio.sleep(0)

                # Then wait for the process to complete
                await self.process.wait()

            # Enforce the overall timeout for the entire operation
            await asyncio.wait_for(_collect_and_wait(), timeout=timeout)

            if self.process.returncode == 0:
                status = SessionStatus.COMPLETED
            else:
                status = SessionStatus.FAILED

        except TimeoutError:
            status = SessionStatus.TIMEOUT
            logger.warning(f"Session timeout after {timeout}s")
            self.process.kill()
            await self.process.wait()

        except asyncio.CancelledError:
            status = SessionStatus.CANCELLED
            self.process.kill()
            await self.process.wait()
            raise

        # Collect stderr if available
        if self.process.stderr:
            try:
                stderr_data = await self.process.stderr.read()
                self._error_lines.append(stderr_data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        ended_at = datetime.now(UTC)
        self._completed = True

        return SessionResult(
            status=status,
            output="\n".join(self._output_lines),
            error="\n".join(self._error_lines) if self._error_lines else None,
            exit_code=self.process.returncode,
            started_at=self.started_at,
            ended_at=ended_at,
        )

    async def cancel(self) -> None:
        """Cancel the running session."""
        if not self._completed and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def stop(self) -> None:
        """Stop the running session (alias for cancel)."""
        await self.cancel()

    @property
    def is_running(self) -> bool:
        """Check if the session is still running."""
        return not self._completed and self.process.returncode is None

    @property
    def output(self) -> str:
        """Get collected output so far."""
        return "\n".join(self._output_lines)
