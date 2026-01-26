"""Safety rails for self-improvement.

Protects critical files and ensures changes are validated
before being applied to a running system.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


class ProtectedFileError(Exception):
    """Raised when attempting to modify a protected file."""

    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Cannot modify protected file {path}: {reason}")


@dataclass
class SafetyConfig:
    """Configuration for safety validation."""

    # Files that cannot be modified without human approval
    protected_files: list[str] = field(
        default_factory=lambda: [
            "src/ringmaster/reload/safety.py",  # This file
            "tests/",  # Tests can't be deleted
            ".ringmaster/",  # Database and state
        ]
    )

    # Require test coverage for self-modifications
    require_tests: bool = True

    # Automatically rollback on test failure
    auto_rollback: bool = True

    # Maximum lines changed in a single modification
    max_lines_changed: int = 500


class SafetyValidator:
    """Validates modifications for safety before applying.

    Implements the safety rails from docs/06-deployment.md:
    - Protected files require human approval
    - Self-improvements require test coverage
    - Automatic rollback on test failure
    """

    def __init__(self, config: SafetyConfig | None = None, project_root: Path | None = None):
        self.config = config or SafetyConfig()
        self.project_root = project_root or Path.cwd()

    def is_protected(self, path: Path) -> bool:
        """Check if a file is protected from automatic modification.

        Args:
            path: Path to check (absolute or relative to project root).

        Returns:
            True if the file is protected.
        """
        # Normalize to relative path
        try:
            rel_path = path.relative_to(self.project_root)
        except ValueError:
            rel_path = path

        path_str = str(rel_path)

        for protected in self.config.protected_files:
            if protected.endswith("/"):
                # Directory protection
                if path_str.startswith(protected) or path_str.startswith(protected.rstrip("/")):
                    return True
            else:
                # File protection
                if path_str == protected or path_str.endswith(f"/{protected}"):
                    return True

        return False

    def validate_modifications(
        self,
        modified_files: list[Path],
        allow_protected: bool = False,
    ) -> tuple[bool, list[str]]:
        """Validate a set of file modifications.

        Args:
            modified_files: List of files that were or will be modified.
            allow_protected: If True, don't raise on protected files.

        Returns:
            Tuple of (is_valid, list of warning messages).

        Raises:
            ProtectedFileError: If a protected file is modified and allow_protected=False.
        """
        warnings: list[str] = []
        protected_files: list[Path] = []

        for path in modified_files:
            if self.is_protected(path):
                protected_files.append(path)
                if not allow_protected:
                    raise ProtectedFileError(
                        path,
                        "This file is protected and requires human approval to modify",
                    )
                warnings.append(f"Protected file modified: {path}")

        # Check total lines changed (would need git diff info)
        # For now, just warn if many files are changed
        if len(modified_files) > 10:
            warnings.append(
                f"Large changeset: {len(modified_files)} files modified. "
                "Consider breaking into smaller changes."
            )

        return len(protected_files) == 0, warnings

    def check_test_coverage(self, modified_files: list[Path]) -> tuple[bool, str | None]:
        """Check if modifications have corresponding test coverage.

        Args:
            modified_files: List of modified source files.

        Returns:
            Tuple of (has_coverage, reason if missing).
        """
        if not self.config.require_tests:
            return True, None

        # Check if any source files need test coverage
        def is_source_file(path: Path) -> bool:
            if path.suffix != ".py":
                return False
            if "test" in path.name:
                return False
            # Check if it's in a src directory (using path parts)
            parts = path.parts
            return "src" in parts or "ringmaster" in parts

        source_files = [f for f in modified_files if is_source_file(f)]

        if not source_files:
            return True, None

        # Check if tests directory exists
        tests_dir = self.project_root / "tests"
        if not tests_dir.exists():
            return False, "No tests directory found"

        # Check if any test files were also modified
        test_files = [f for f in modified_files if "test" in f.name.lower()]
        if not test_files:
            return False, "Source files modified but no test files included"

        return True, None

    def should_auto_rollback(self) -> bool:
        """Check if automatic rollback is enabled."""
        return self.config.auto_rollback
