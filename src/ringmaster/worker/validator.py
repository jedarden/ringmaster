"""Task validation for code review stage.

Based on docs/08-open-architecture.md Section 3:
- Run test suite after worker completion
- Run static analysis (linting, type checking)
- Auto-approve if checks pass
- Optionally assign validation worker for human review

This module provides deterministic validation (tests, lint) to
automatically transition tasks from REVIEW to DONE status.
"""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Status of a validation check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Check not applicable or disabled
    ERROR = "error"  # Check itself failed to run


@dataclass
class ValidationCheck:
    """Result of a single validation check."""

    name: str
    status: ValidationStatus = ValidationStatus.SKIPPED  # Default to SKIPPED
    message: str = ""
    duration_seconds: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Combined result of all validation checks."""

    checks: list[ValidationCheck] = field(default_factory=list)
    overall_passed: bool = False
    needs_human_review: bool = False
    review_reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed_checks(self) -> list[ValidationCheck]:
        """Get all checks that passed."""
        return [c for c in self.checks if c.status == ValidationStatus.PASSED]

    @property
    def failed_checks(self) -> list[ValidationCheck]:
        """Get all checks that failed."""
        return [c for c in self.checks if c.status == ValidationStatus.FAILED]

    @property
    def summary(self) -> str:
        """Get a summary of the validation result."""
        total = len(self.checks)
        passed = len(self.passed_checks)
        failed = len(self.failed_checks)

        if self.overall_passed:
            return f"Validation passed ({passed}/{total} checks)"
        else:
            return f"Validation failed ({failed} failed, {passed} passed)"


@dataclass
class ValidatorConfig:
    """Configuration for the task validator."""

    # Test suite settings
    run_tests: bool = True
    test_command: str | None = None  # Auto-detect if None
    test_timeout: int = 300  # 5 minutes

    # Linting settings
    run_linting: bool = True
    lint_command: str | None = None  # Auto-detect if None
    lint_timeout: int = 120  # 2 minutes

    # Type checking settings (optional)
    run_type_check: bool = False
    type_check_command: str | None = None
    type_check_timeout: int = 120

    # Review requirements
    require_human_review: bool = False  # Always require human review?
    human_review_patterns: list[str] = field(
        default_factory=lambda: [
            "security",
            "auth",
            "payment",
            "crypto",
            "password",
            "secret",
        ]
    )


class TaskValidator:
    """Validates completed tasks before marking them as DONE.

    The validator runs deterministic checks (tests, lint) to ensure
    code quality before auto-approving tasks. Tasks that fail validation
    can be sent back to the worker for fixing.
    """

    def __init__(
        self,
        config: ValidatorConfig | None = None,
        working_dir: Path | None = None,
    ):
        self.config = config or ValidatorConfig()
        self.working_dir = working_dir or Path.cwd()

    async def validate_task(
        self,
        task_title: str,
        task_description: str,
        working_dir: Path | None = None,
    ) -> ValidationResult:
        """Validate a completed task.

        Runs configured checks and returns an overall result. The validation
        is deterministic - no LLM calls are made.

        Args:
            task_title: Title of the task (for pattern matching).
            task_description: Description of the task.
            working_dir: Directory where code changes were made.

        Returns:
            ValidationResult with all check outcomes.
        """
        work_dir = working_dir or self.working_dir
        result = ValidationResult()

        # Check if human review is required based on patterns
        task_text = f"{task_title} {task_description}".lower()
        for pattern in self.config.human_review_patterns:
            if pattern in task_text:
                result.needs_human_review = True
                result.review_reason = f"Task contains sensitive pattern: '{pattern}'"
                break

        # Run test suite
        if self.config.run_tests:
            test_check = await self._run_tests(work_dir)
            result.checks.append(test_check)

        # Run linting
        if self.config.run_linting:
            lint_check = await self._run_linting(work_dir)
            result.checks.append(lint_check)

        # Run type checking (optional)
        if self.config.run_type_check:
            type_check = await self._run_type_check(work_dir)
            result.checks.append(type_check)

        # Determine overall result
        failed_checks = result.failed_checks
        if failed_checks:
            result.overall_passed = False
        elif self.config.require_human_review:
            result.overall_passed = False
            result.needs_human_review = True
            result.review_reason = "Human review required by configuration"
        else:
            result.overall_passed = not result.needs_human_review

        return result

    async def _run_tests(self, working_dir: Path) -> ValidationCheck:
        """Run the test suite.

        Auto-detects test runner if not configured:
        - pytest for Python
        - npm test for Node.js
        - cargo test for Rust
        """
        start_time = datetime.now(UTC)
        check = ValidationCheck(name="tests")

        # Detect test command if not configured
        command = self.config.test_command
        if not command:
            command = self._detect_test_command(working_dir)

        if not command:
            check.status = ValidationStatus.SKIPPED
            check.message = "No test command detected"
            return check

        # Run tests
        try:
            exit_code, output = await self._run_command(
                command, working_dir, self.config.test_timeout
            )

            check.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()
            check.details["command"] = command
            check.details["exit_code"] = exit_code
            check.details["output_preview"] = output[:1000] if output else ""

            if exit_code == 0:
                check.status = ValidationStatus.PASSED
                check.message = "All tests passed"
            else:
                check.status = ValidationStatus.FAILED
                check.message = f"Tests failed (exit code {exit_code})"

        except TimeoutError:
            check.status = ValidationStatus.ERROR
            check.message = f"Test command timed out after {self.config.test_timeout}s"

        except Exception as e:
            check.status = ValidationStatus.ERROR
            check.message = f"Test command error: {str(e)}"
            logger.exception(f"Error running tests in {working_dir}")

        return check

    async def _run_linting(self, working_dir: Path) -> ValidationCheck:
        """Run linting/formatting checks.

        Auto-detects linter if not configured:
        - ruff for Python
        - eslint for Node.js
        - cargo clippy for Rust
        """
        start_time = datetime.now(UTC)
        check = ValidationCheck(name="linting")

        # Detect lint command if not configured
        command = self.config.lint_command
        if not command:
            command = self._detect_lint_command(working_dir)

        if not command:
            check.status = ValidationStatus.SKIPPED
            check.message = "No lint command detected"
            return check

        # Run linting
        try:
            exit_code, output = await self._run_command(
                command, working_dir, self.config.lint_timeout
            )

            check.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()
            check.details["command"] = command
            check.details["exit_code"] = exit_code
            check.details["output_preview"] = output[:1000] if output else ""

            if exit_code == 0:
                check.status = ValidationStatus.PASSED
                check.message = "Linting passed"
            else:
                check.status = ValidationStatus.FAILED
                check.message = f"Linting failed (exit code {exit_code})"

        except TimeoutError:
            check.status = ValidationStatus.ERROR
            check.message = f"Lint command timed out after {self.config.lint_timeout}s"

        except Exception as e:
            check.status = ValidationStatus.ERROR
            check.message = f"Lint command error: {str(e)}"
            logger.exception(f"Error running linting in {working_dir}")

        return check

    async def _run_type_check(self, working_dir: Path) -> ValidationCheck:
        """Run type checking.

        Auto-detects type checker if not configured:
        - mypy for Python
        - tsc for TypeScript
        """
        start_time = datetime.now(UTC)
        check = ValidationCheck(name="type_check")

        # Detect type check command if not configured
        command = self.config.type_check_command
        if not command:
            command = self._detect_type_check_command(working_dir)

        if not command:
            check.status = ValidationStatus.SKIPPED
            check.message = "No type check command detected"
            return check

        # Run type checking
        try:
            exit_code, output = await self._run_command(
                command, working_dir, self.config.type_check_timeout
            )

            check.duration_seconds = (datetime.now(UTC) - start_time).total_seconds()
            check.details["command"] = command
            check.details["exit_code"] = exit_code
            check.details["output_preview"] = output[:1000] if output else ""

            if exit_code == 0:
                check.status = ValidationStatus.PASSED
                check.message = "Type checking passed"
            else:
                check.status = ValidationStatus.FAILED
                check.message = f"Type checking failed (exit code {exit_code})"

        except TimeoutError:
            check.status = ValidationStatus.ERROR
            check.message = f"Type check command timed out after {self.config.type_check_timeout}s"

        except Exception as e:
            check.status = ValidationStatus.ERROR
            check.message = f"Type check command error: {str(e)}"
            logger.exception(f"Error running type check in {working_dir}")

        return check

    def _detect_test_command(self, working_dir: Path) -> str | None:
        """Auto-detect the appropriate test command for the project."""
        # Use sys.executable for portability across Python installations
        python_exe = sys.executable

        # Python
        if (working_dir / "pytest.ini").exists() or (working_dir / "pyproject.toml").exists():
            return f"{python_exe} -m pytest --tb=short -q"

        if (working_dir / "setup.py").exists():
            return f"{python_exe} -m pytest --tb=short -q"

        # Node.js
        if (working_dir / "package.json").exists():
            return "npm test"

        # Rust
        if (working_dir / "Cargo.toml").exists():
            return "cargo test"

        # Go
        if (working_dir / "go.mod").exists():
            return "go test ./..."

        return None

    def _detect_lint_command(self, working_dir: Path) -> str | None:
        """Auto-detect the appropriate lint command for the project."""
        # Use sys.executable for portability across Python installations
        python_exe = sys.executable

        # Python
        if (working_dir / "ruff.toml").exists() or (working_dir / "pyproject.toml").exists():
            return f"{python_exe} -m ruff check ."

        if (working_dir / ".flake8").exists() or (working_dir / "setup.cfg").exists():
            return f"{python_exe} -m flake8 ."

        # Node.js
        if (working_dir / ".eslintrc.js").exists() or (working_dir / ".eslintrc.json").exists():
            return "npx eslint ."

        if (working_dir / "eslint.config.js").exists():
            return "npx eslint ."

        # Rust
        if (working_dir / "Cargo.toml").exists():
            return "cargo clippy -- -D warnings"

        # Go
        if (working_dir / "go.mod").exists():
            return "golangci-lint run"

        return None

    def _detect_type_check_command(self, working_dir: Path) -> str | None:
        """Auto-detect the appropriate type check command for the project."""
        # Use sys.executable for portability across Python installations
        python_exe = sys.executable

        # Python
        if (working_dir / "mypy.ini").exists() or (working_dir / "pyproject.toml").exists():
            return f"{python_exe} -m mypy ."

        # TypeScript
        if (working_dir / "tsconfig.json").exists():
            return "npx tsc --noEmit"

        return None

    async def _run_command(
        self,
        command: str,
        working_dir: Path,
        timeout: int,
    ) -> tuple[int, str]:
        """Run a shell command and return exit code + output.

        Args:
            command: Command to run.
            working_dir: Directory to run in.
            timeout: Timeout in seconds.

        Returns:
            Tuple of (exit_code, combined_output).
        """
        logger.debug(f"Running command: {command} in {working_dir}")

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            return proc.returncode or 0, output

        except TimeoutError:
            proc.kill()
            raise


# Convenience function for validating a task
async def validate_task(
    task_title: str,
    task_description: str,
    working_dir: Path,
    config: ValidatorConfig | None = None,
) -> ValidationResult:
    """Validate a completed task.

    This is a convenience function that creates a TaskValidator and runs validation.

    Args:
        task_title: Title of the task.
        task_description: Description of the task.
        working_dir: Directory where code changes were made.
        config: Optional validator configuration.

    Returns:
        ValidationResult with all check outcomes.
    """
    validator = TaskValidator(config=config, working_dir=working_dir)
    return await validator.validate_task(task_title, task_description, working_dir)
