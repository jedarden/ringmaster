"""File change watching for hot-reload.

Watches for changes to:
- Configuration files (ringmaster.toml)
- Python source files
- Any specified watch directories
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a detected file change."""

    path: Path
    change_type: str  # "modified", "created", "deleted"
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ConfigWatcher:
    """Watches a configuration file for changes.

    Uses modification time to detect changes, with optional
    content hash for additional verification.
    """

    def __init__(self, path: str | Path, use_hash: bool = False):
        self.path = Path(path)
        self.use_hash = use_hash
        self._last_mtime: float = 0
        self._last_hash: str | None = None

        # Initialize state if file exists
        if self.path.exists():
            self._last_mtime = self.path.stat().st_mtime
            if self.use_hash:
                self._last_hash = self._compute_hash()

    def _compute_hash(self) -> str | None:
        """Compute SHA256 hash of file content."""
        if not self.path.exists():
            return None
        content = self.path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def check_changed(self) -> bool:
        """Check if the config file has changed.

        Returns:
            True if file has been modified since last check.
        """
        if not self.path.exists():
            return False

        mtime = self.path.stat().st_mtime
        if mtime > self._last_mtime:
            self._last_mtime = mtime

            if self.use_hash:
                new_hash = self._compute_hash()
                if new_hash != self._last_hash:
                    self._last_hash = new_hash
                    return True
                return False

            return True

        return False


class FileChangeWatcher:
    """Watches directories for file changes.

    Scans directories periodically to detect:
    - New files
    - Modified files
    - Deleted files

    Uses modification times and file hashes for accurate detection.
    """

    def __init__(
        self,
        watch_dirs: list[str | Path],
        patterns: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
    ):
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self.patterns = patterns or ["*.py"]
        self.ignore_patterns = ignore_patterns or [
            "__pycache__",
            "*.pyc",
            ".git",
            ".venv",
            "*.egg-info",
        ]

        # State tracking
        self._file_states: dict[Path, tuple[float, str]] = {}  # path -> (mtime, hash)
        self._initialized = False

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)
        return any(pattern in path_str for pattern in self.ignore_patterns)

    def _matches_pattern(self, path: Path) -> bool:
        """Check if path matches watch patterns."""
        return any(path.match(pattern) for pattern in self.patterns)

    def _compute_hash(self, path: Path) -> str:
        """Compute SHA256 hash of file content."""
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _scan_files(self) -> dict[Path, tuple[float, str]]:
        """Scan all watched directories for matching files."""
        files: dict[Path, tuple[float, str]] = {}

        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue

            for path in watch_dir.rglob("*"):
                if not path.is_file():
                    continue
                if self._should_ignore(path):
                    continue
                if not self._matches_pattern(path):
                    continue

                try:
                    mtime = path.stat().st_mtime
                    file_hash = self._compute_hash(path)
                    files[path] = (mtime, file_hash)
                except OSError as e:
                    logger.debug(f"Error scanning {path}: {e}")

        return files

    def initialize(self) -> None:
        """Initialize the watcher state by scanning current files."""
        self._file_states = self._scan_files()
        self._initialized = True
        logger.info(f"FileChangeWatcher initialized with {len(self._file_states)} files")

    def detect_changes(self) -> list[FileChange]:
        """Detect changes since last scan.

        Returns:
            List of FileChange objects describing detected changes.
        """
        if not self._initialized:
            self.initialize()
            return []  # First run, no changes to report

        current_files = self._scan_files()
        changes: list[FileChange] = []

        # Check for modified or new files
        for path, (_mtime, file_hash) in current_files.items():
            if path not in self._file_states:
                changes.append(FileChange(path=path, change_type="created"))
            else:
                _old_mtime, old_hash = self._file_states[path]
                if file_hash != old_hash:
                    changes.append(FileChange(path=path, change_type="modified"))

        # Check for deleted files
        for path in self._file_states:
            if path not in current_files:
                changes.append(FileChange(path=path, change_type="deleted"))

        # Update state
        self._file_states = current_files

        return changes

    async def watch_loop(
        self,
        callback,
        poll_interval: float = 2.0,
        debounce_seconds: float = 1.0,
    ) -> None:
        """Run a continuous watch loop.

        Args:
            callback: Async function to call with list of changes.
            poll_interval: Seconds between directory scans.
            debounce_seconds: Seconds to wait for additional changes before triggering.
        """
        self.initialize()
        pending_changes: list[FileChange] = []
        last_change_time: datetime | None = None

        while True:
            changes = self.detect_changes()

            if changes:
                pending_changes.extend(changes)
                last_change_time = datetime.now(UTC)

            # Debounce: wait for changes to settle
            if (
                pending_changes
                and last_change_time
                and (datetime.now(UTC) - last_change_time).total_seconds()
                > debounce_seconds
            ):
                logger.info(f"Detected {len(pending_changes)} file changes")
                await callback(pending_changes)
                pending_changes = []
                last_change_time = None

            await asyncio.sleep(poll_interval)
