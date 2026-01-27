"""Tests for task validation module."""

import tempfile
from pathlib import Path

import pytest

from ringmaster.worker.validator import (
    TaskValidator,
    ValidationCheck,
    ValidationResult,
    ValidationStatus,
    ValidatorConfig,
    validate_task,
)


class TestValidatorConfig:
    """Test ValidatorConfig defaults."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ValidatorConfig()

        assert config.run_tests is True
        assert config.run_linting is True
        assert config.run_type_check is False
        assert config.require_human_review is False
        assert config.test_timeout == 300
        assert config.lint_timeout == 120
        assert "security" in config.human_review_patterns

    def test_custom_config(self):
        """Test custom configuration."""
        config = ValidatorConfig(
            run_tests=False,
            test_command="pytest -x",
            require_human_review=True,
        )

        assert config.run_tests is False
        assert config.test_command == "pytest -x"
        assert config.require_human_review is True


class TestValidationCheck:
    """Test ValidationCheck dataclass."""

    def test_check_creation(self):
        """Test creating a validation check."""
        check = ValidationCheck(
            name="tests",
            status=ValidationStatus.PASSED,
            message="All tests passed",
            duration_seconds=5.5,
        )

        assert check.name == "tests"
        assert check.status == ValidationStatus.PASSED
        assert check.message == "All tests passed"
        assert check.duration_seconds == 5.5


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_empty_result(self):
        """Test empty validation result."""
        result = ValidationResult()

        assert result.checks == []
        assert result.overall_passed is False
        assert result.needs_human_review is False
        assert len(result.passed_checks) == 0
        assert len(result.failed_checks) == 0

    def test_passed_result(self):
        """Test result with passed checks."""
        result = ValidationResult(
            checks=[
                ValidationCheck(name="tests", status=ValidationStatus.PASSED, message="OK"),
                ValidationCheck(name="lint", status=ValidationStatus.PASSED, message="OK"),
            ],
            overall_passed=True,
        )

        assert len(result.passed_checks) == 2
        assert len(result.failed_checks) == 0
        assert "passed" in result.summary.lower()

    def test_failed_result(self):
        """Test result with failed checks."""
        result = ValidationResult(
            checks=[
                ValidationCheck(name="tests", status=ValidationStatus.FAILED, message="1 failed"),
                ValidationCheck(name="lint", status=ValidationStatus.PASSED, message="OK"),
            ],
            overall_passed=False,
        )

        assert len(result.passed_checks) == 1
        assert len(result.failed_checks) == 1
        assert "failed" in result.summary.lower()


class TestTaskValidator:
    """Test TaskValidator class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_detect_test_command_python(self, temp_dir: Path):
        """Test Python test command detection."""
        # Create pyproject.toml
        (temp_dir / "pyproject.toml").write_text("[tool.pytest]\n")

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_test_command(temp_dir)

        assert command is not None
        assert "pytest" in command

    def test_detect_test_command_nodejs(self, temp_dir: Path):
        """Test Node.js test command detection."""
        (temp_dir / "package.json").write_text('{"name": "test"}\n')

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_test_command(temp_dir)

        assert command is not None
        assert "npm test" in command

    def test_detect_test_command_rust(self, temp_dir: Path):
        """Test Rust test command detection."""
        (temp_dir / "Cargo.toml").write_text('[package]\nname = "test"\n')

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_test_command(temp_dir)

        assert command is not None
        assert "cargo test" in command

    def test_detect_test_command_none(self, temp_dir: Path):
        """Test no test command detection for empty directory."""
        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_test_command(temp_dir)

        assert command is None

    def test_detect_lint_command_ruff(self, temp_dir: Path):
        """Test ruff lint command detection."""
        (temp_dir / "ruff.toml").write_text("[lint]\n")

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_lint_command(temp_dir)

        assert command is not None
        assert "ruff" in command

    def test_detect_lint_command_eslint(self, temp_dir: Path):
        """Test eslint command detection."""
        (temp_dir / ".eslintrc.js").write_text("module.exports = {}\n")

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_lint_command(temp_dir)

        assert command is not None
        assert "eslint" in command

    def test_detect_type_check_mypy(self, temp_dir: Path):
        """Test mypy type check command detection."""
        (temp_dir / "mypy.ini").write_text("[mypy]\n")

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_type_check_command(temp_dir)

        assert command is not None
        assert "mypy" in command

    def test_detect_type_check_typescript(self, temp_dir: Path):
        """Test TypeScript type check command detection."""
        (temp_dir / "tsconfig.json").write_text('{"compilerOptions": {}}\n')

        validator = TaskValidator(working_dir=temp_dir)
        command = validator._detect_type_check_command(temp_dir)

        assert command is not None
        assert "tsc" in command


class TestValidatorSensitivePatterns:
    """Test sensitive pattern detection."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_security_pattern_triggers_human_review(self, temp_dir: Path):
        """Test that security-related tasks require human review."""
        config = ValidatorConfig(run_tests=False, run_linting=False)
        validator = TaskValidator(config=config, working_dir=temp_dir)

        result = await validator.validate_task(
            task_title="Fix security vulnerability in auth",
            task_description="Update password hashing",
            working_dir=temp_dir,
        )

        assert result.needs_human_review is True
        assert "security" in result.review_reason.lower() or "password" in result.review_reason.lower()

    @pytest.mark.asyncio
    async def test_payment_pattern_triggers_human_review(self, temp_dir: Path):
        """Test that payment-related tasks require human review."""
        config = ValidatorConfig(run_tests=False, run_linting=False)
        validator = TaskValidator(config=config, working_dir=temp_dir)

        result = await validator.validate_task(
            task_title="Update payment processing",
            task_description="Fix credit card validation",
            working_dir=temp_dir,
        )

        assert result.needs_human_review is True
        assert "payment" in result.review_reason.lower()

    @pytest.mark.asyncio
    async def test_normal_task_no_human_review(self, temp_dir: Path):
        """Test that normal tasks don't require human review."""
        config = ValidatorConfig(run_tests=False, run_linting=False)
        validator = TaskValidator(config=config, working_dir=temp_dir)

        result = await validator.validate_task(
            task_title="Add unit tests",
            task_description="Increase test coverage",
            working_dir=temp_dir,
        )

        assert result.needs_human_review is False
        # With no checks, should pass
        assert result.overall_passed is True


class TestValidatorCommandExecution:
    """Test command execution in validator."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_run_command_success(self, temp_dir: Path):
        """Test running a successful command."""
        validator = TaskValidator(working_dir=temp_dir)
        exit_code, output = await validator._run_command(
            "echo 'hello world'",
            temp_dir,
            timeout=30,
        )

        assert exit_code == 0
        assert "hello world" in output

    @pytest.mark.asyncio
    async def test_run_command_failure(self, temp_dir: Path):
        """Test running a failing command."""
        validator = TaskValidator(working_dir=temp_dir)
        exit_code, output = await validator._run_command(
            "exit 1",
            temp_dir,
            timeout=30,
        )

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_run_command_timeout(self, temp_dir: Path):
        """Test command timeout."""
        validator = TaskValidator(working_dir=temp_dir)

        with pytest.raises(TimeoutError):
            await validator._run_command(
                "sleep 10",
                temp_dir,
                timeout=1,
            )


class TestValidateTaskFunction:
    """Test the convenience validate_task function."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_validate_task_convenience_function(self, temp_dir: Path):
        """Test the standalone validate_task function."""
        config = ValidatorConfig(run_tests=False, run_linting=False)

        result = await validate_task(
            task_title="Add feature",
            task_description="New feature implementation",
            working_dir=temp_dir,
            config=config,
        )

        assert isinstance(result, ValidationResult)
        assert result.overall_passed is True  # No checks = pass


class TestValidatorWithRealTests:
    """Test validator with actual test execution."""

    @pytest.fixture
    def python_project(self):
        """Create a temporary Python project for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create pyproject.toml
            (project_dir / "pyproject.toml").write_text(
                """
[tool.pytest.ini_options]
pythonpath = ["."]
"""
            )

            # Create a simple passing test
            (project_dir / "test_example.py").write_text(
                """
def test_always_passes():
    assert True
"""
            )

            yield project_dir

    @pytest.mark.asyncio
    async def test_run_tests_passing(self, python_project: Path):
        """Test running tests that pass."""
        config = ValidatorConfig(run_linting=False)
        validator = TaskValidator(config=config, working_dir=python_project)

        check = await validator._run_tests(python_project)

        assert check.status == ValidationStatus.PASSED
        assert "passed" in check.message.lower()

    @pytest.mark.asyncio
    async def test_skipped_when_no_test_command(self):
        """Test skipping when no test command detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            config = ValidatorConfig(test_command=None)
            validator = TaskValidator(config=config, working_dir=project_dir)

            check = await validator._run_tests(project_dir)

            assert check.status == ValidationStatus.SKIPPED
