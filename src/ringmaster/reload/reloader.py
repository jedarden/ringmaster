"""Hot-reload implementation for self-improvement.

Handles:
- Running tests on code changes
- Reloading Python modules
- Signaling component restarts
- Rollback on failure
"""

import asyncio
import importlib
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from ringmaster import __version__
from ringmaster.reload.safety import SafetyConfig, SafetyValidator
from ringmaster.reload.watcher import FileChange

logger = logging.getLogger(__name__)


class ReloadStatus(Enum):
    """Status of a reload operation."""

    SUCCESS = "success"
    FAILED_TESTS = "failed_tests"
    FAILED_SAFETY = "failed_safety"
    FAILED_IMPORT = "failed_import"
    ROLLED_BACK = "rolled_back"


@dataclass
class ReloadResult:
    """Result of a hot-reload operation."""

    status: ReloadStatus
    changes: list[FileChange]
    test_output: str | None = None
    error_message: str | None = None
    reloaded_modules: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class HotReloader:
    """Manages hot-reload of Ringmaster components.

    Flow:
    1. Detect file changes (from FileChangeWatcher)
    2. Validate safety (protected files, test coverage)
    3. Run tests
    4. If tests pass: reload affected modules
    5. If tests fail: rollback changes (if auto_rollback enabled)
    """

    def __init__(
        self,
        project_root: Path | None = None,
        safety_config: SafetyConfig | None = None,
        test_command: list[str] | None = None,
        venv_python: Path | None = None,
    ):
        self.project_root = project_root or Path.cwd()
        self.safety = SafetyValidator(safety_config, self.project_root)
        self.test_command = test_command or ["pytest", "tests/", "-x", "--tb=short"]
        self.venv_python = venv_python

        # Track reload history
        self._reload_history: list[ReloadResult] = []

    def _get_python_executable(self) -> str:
        """Get the Python executable path."""
        if self.venv_python:
            return str(self.venv_python)
        return sys.executable

    async def run_tests(self, timeout: float = 300.0) -> tuple[bool, str]:
        """Run the test suite.

        Args:
            timeout: Maximum seconds to wait for tests.

        Returns:
            Tuple of (tests_passed, output).
        """
        python = self._get_python_executable()
        cmd = [python, "-m"] + self.test_command

        logger.info(f"Running tests: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            output = stdout.decode() if stdout else ""
            success = process.returncode == 0

            if success:
                logger.info("Tests passed")
            else:
                logger.warning(f"Tests failed with exit code {process.returncode}")

            return success, output

        except TimeoutError:
            logger.error(f"Tests timed out after {timeout} seconds")
            if process:
                process.kill()
            return False, f"Tests timed out after {timeout} seconds"

        except Exception as e:
            logger.error(f"Error running tests: {e}")
            return False, str(e)

    def _path_to_module(self, path: Path) -> str | None:
        """Convert a file path to a Python module name.

        Args:
            path: Path to a Python file.

        Returns:
            Module name (e.g., "ringmaster.reload.watcher") or None.
        """
        if path.suffix != ".py":
            return None

        try:
            # Try to make path relative to project root
            rel_path = path.relative_to(self.project_root)
        except ValueError:
            rel_path = path

        # Remove src/ prefix if present
        parts = rel_path.parts
        if parts and parts[0] == "src":
            parts = parts[1:]

        # Convert path to module name
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts = (*parts[:-1], parts[-1].replace(".py", ""))

        return ".".join(parts)

    def reload_module(self, module_name: str) -> bool:
        """Reload a Python module.

        Args:
            module_name: Full module name (e.g., "ringmaster.reload.watcher").

        Returns:
            True if reload succeeded.
        """
        if module_name not in sys.modules:
            logger.debug(f"Module {module_name} not loaded, skipping reload")
            return True

        try:
            module = sys.modules[module_name]
            importlib.reload(module)
            logger.info(f"Reloaded module: {module_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to reload module {module_name}: {e}")
            return False

    async def rollback_changes(self, files: list[Path]) -> bool:
        """Rollback changes using git.

        Args:
            files: List of files to rollback.

        Returns:
            True if rollback succeeded.
        """
        if not files:
            return True

        file_paths = [str(f) for f in files]
        cmd = ["git", "checkout", "--"] + file_paths

        logger.info(f"Rolling back {len(files)} files")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Rollback failed: {stderr.decode()}")
                return False

            logger.info("Rollback completed")
            return True

        except Exception as e:
            logger.error(f"Error during rollback: {e}")
            return False

    async def process_changes(
        self,
        changes: list[FileChange],
        skip_tests: bool = False,
        allow_protected: bool = False,
    ) -> ReloadResult:
        """Process file changes and perform hot-reload.

        Args:
            changes: List of detected file changes.
            skip_tests: Skip running tests (dangerous!).
            allow_protected: Allow modifying protected files.

        Returns:
            ReloadResult describing the outcome.
        """
        modified_paths = [c.path for c in changes]
        logger.info(f"Processing {len(changes)} file changes")

        # Step 1: Safety validation
        try:
            is_safe, warnings = self.safety.validate_modifications(
                modified_paths, allow_protected=allow_protected
            )
            for warning in warnings:
                logger.warning(warning)
        except Exception as e:
            logger.error(f"Safety validation failed: {e}")
            result = ReloadResult(
                status=ReloadStatus.FAILED_SAFETY,
                changes=changes,
                error_message=str(e),
            )
            self._reload_history.append(result)
            return result

        # Step 2: Check test coverage requirement
        has_coverage, coverage_reason = self.safety.check_test_coverage(modified_paths)
        if not has_coverage and not skip_tests:
            logger.warning(f"Test coverage check failed: {coverage_reason}")
            # Continue anyway, but log the warning

        # Step 3: Run tests
        test_output = None
        if not skip_tests:
            tests_passed, test_output = await self.run_tests()

            if not tests_passed:
                logger.error("Tests failed, reload aborted")

                # Rollback if enabled
                if self.safety.should_auto_rollback():
                    await self.rollback_changes(modified_paths)
                    result = ReloadResult(
                        status=ReloadStatus.ROLLED_BACK,
                        changes=changes,
                        test_output=test_output,
                        error_message="Tests failed, changes rolled back",
                    )
                else:
                    result = ReloadResult(
                        status=ReloadStatus.FAILED_TESTS,
                        changes=changes,
                        test_output=test_output,
                        error_message="Tests failed",
                    )

                self._reload_history.append(result)
                return result

        # Step 4: Reload modules
        reloaded_modules: list[str] = []
        failed_modules: list[str] = []

        for change in changes:
            if change.change_type == "deleted":
                continue  # Can't reload deleted modules

            module_name = self._path_to_module(change.path)
            if module_name:
                if self.reload_module(module_name):
                    reloaded_modules.append(module_name)
                else:
                    failed_modules.append(module_name)

        # Check for import failures
        if failed_modules:
            logger.error(f"Failed to reload modules: {failed_modules}")
            result = ReloadResult(
                status=ReloadStatus.FAILED_IMPORT,
                changes=changes,
                test_output=test_output,
                error_message=f"Failed to reload: {', '.join(failed_modules)}",
                reloaded_modules=reloaded_modules,
            )
            self._reload_history.append(result)
            return result

        # Success!
        logger.info(f"Hot-reload complete: {len(reloaded_modules)} modules reloaded (ringmaster v{__version__})")
        result = ReloadResult(
            status=ReloadStatus.SUCCESS,
            changes=changes,
            test_output=test_output,
            reloaded_modules=reloaded_modules,
        )
        self._reload_history.append(result)
        return result

    def get_reload_history(self, limit: int = 10) -> list[ReloadResult]:
        """Get recent reload history.

        Args:
            limit: Maximum number of results to return.

        Returns:
            List of recent ReloadResults.
        """
        return self._reload_history[-limit:]
