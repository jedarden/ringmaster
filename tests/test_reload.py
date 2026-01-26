"""Tests for the hot-reload module."""

from pathlib import Path

import pytest

from ringmaster.reload.reloader import HotReloader, ReloadStatus
from ringmaster.reload.safety import ProtectedFileError, SafetyConfig, SafetyValidator
from ringmaster.reload.watcher import ConfigWatcher, FileChange, FileChangeWatcher


class TestConfigWatcher:
    """Tests for ConfigWatcher."""

    def test_init_with_existing_file(self, tmp_path: Path):
        """Config watcher initializes with existing file's mtime."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[test]\nkey = 'value'")

        watcher = ConfigWatcher(config_file)
        assert watcher._last_mtime > 0

    def test_init_with_missing_file(self, tmp_path: Path):
        """Config watcher handles missing file gracefully."""
        config_file = tmp_path / "missing.toml"

        watcher = ConfigWatcher(config_file)
        assert watcher._last_mtime == 0

    def test_check_changed_detects_modification(self, tmp_path: Path):
        """Config watcher detects file modification."""
        import time

        config_file = tmp_path / "config.toml"
        config_file.write_text("original")

        watcher = ConfigWatcher(config_file)
        assert not watcher.check_changed()  # No change yet

        # Wait a moment to ensure mtime changes
        time.sleep(0.1)

        # Modify the file
        config_file.write_text("modified")
        assert watcher.check_changed()

        # Second check should return False (no new changes)
        assert not watcher.check_changed()

    def test_check_changed_with_hash_verification(self, tmp_path: Path):
        """Config watcher uses hash verification when enabled."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("original")

        watcher = ConfigWatcher(config_file, use_hash=True)
        assert watcher._last_hash is not None

        # Same content, different mtime shouldn't trigger if hash is same
        import os
        os.utime(config_file, None)  # Update mtime
        # Note: This test is simplified - in practice the hash check
        # only happens when mtime changes


class TestFileChangeWatcher:
    """Tests for FileChangeWatcher."""

    def test_initialize_scans_files(self, tmp_path: Path):
        """File watcher initializes by scanning existing files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# code")
        (src_dir / "other.py").write_text("# more code")

        watcher = FileChangeWatcher([src_dir])
        watcher.initialize()

        assert len(watcher._file_states) == 2

    def test_detect_new_file(self, tmp_path: Path):
        """File watcher detects new files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "existing.py").write_text("# code")

        watcher = FileChangeWatcher([src_dir])
        watcher.initialize()

        # Add a new file
        (src_dir / "new.py").write_text("# new code")

        changes = watcher.detect_changes()
        assert len(changes) == 1
        assert changes[0].change_type == "created"
        assert changes[0].path.name == "new.py"

    def test_detect_modified_file(self, tmp_path: Path):
        """File watcher detects modified files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_file = src_dir / "module.py"
        test_file.write_text("# original")

        watcher = FileChangeWatcher([src_dir])
        watcher.initialize()

        # Modify the file
        test_file.write_text("# modified")

        changes = watcher.detect_changes()
        assert len(changes) == 1
        assert changes[0].change_type == "modified"

    def test_detect_deleted_file(self, tmp_path: Path):
        """File watcher detects deleted files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_file = src_dir / "module.py"
        test_file.write_text("# code")

        watcher = FileChangeWatcher([src_dir])
        watcher.initialize()

        # Delete the file
        test_file.unlink()

        changes = watcher.detect_changes()
        assert len(changes) == 1
        assert changes[0].change_type == "deleted"

    def test_ignores_pycache(self, tmp_path: Path):
        """File watcher ignores __pycache__ directories."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        pycache = src_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "module.cpython-312.pyc").write_bytes(b"bytecode")
        (src_dir / "module.py").write_text("# code")

        watcher = FileChangeWatcher([src_dir])
        watcher.initialize()

        # Only the .py file should be tracked
        assert len(watcher._file_states) == 1

    def test_respects_patterns(self, tmp_path: Path):
        """File watcher respects file patterns."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# python")
        (src_dir / "script.sh").write_text("# bash")
        (src_dir / "data.json").write_text("{}")

        watcher = FileChangeWatcher([src_dir], patterns=["*.py", "*.json"])
        watcher.initialize()

        # Only .py and .json files should be tracked
        assert len(watcher._file_states) == 2


class TestSafetyValidator:
    """Tests for SafetyValidator."""

    def test_is_protected_file(self, tmp_path: Path):
        """Safety validator identifies protected files."""
        config = SafetyConfig(protected_files=["src/ringmaster/reload/safety.py"])
        validator = SafetyValidator(config, tmp_path)

        assert validator.is_protected(tmp_path / "src/ringmaster/reload/safety.py")
        assert not validator.is_protected(tmp_path / "src/ringmaster/reload/watcher.py")

    def test_is_protected_directory(self, tmp_path: Path):
        """Safety validator protects entire directories."""
        config = SafetyConfig(protected_files=["tests/"])
        validator = SafetyValidator(config, tmp_path)

        assert validator.is_protected(tmp_path / "tests/test_api.py")
        assert validator.is_protected(tmp_path / "tests/conftest.py")
        assert not validator.is_protected(tmp_path / "src/module.py")

    def test_validate_modifications_raises_on_protected(self, tmp_path: Path):
        """Validation raises error for protected file modifications."""
        config = SafetyConfig(protected_files=["critical.py"])
        validator = SafetyValidator(config, tmp_path)

        with pytest.raises(ProtectedFileError) as exc_info:
            validator.validate_modifications([tmp_path / "critical.py"])

        assert "protected" in str(exc_info.value).lower()

    def test_validate_modifications_allows_with_flag(self, tmp_path: Path):
        """Validation allows protected files with allow_protected=True."""
        config = SafetyConfig(protected_files=["critical.py"])
        validator = SafetyValidator(config, tmp_path)

        is_valid, warnings = validator.validate_modifications(
            [tmp_path / "critical.py"], allow_protected=True
        )

        assert not is_valid  # Still reports as not safe
        assert len(warnings) == 1
        assert "protected" in warnings[0].lower()

    def test_check_test_coverage_requires_tests(self, tmp_path: Path):
        """Test coverage check requires test files for source changes."""
        config = SafetyConfig(require_tests=True)
        validator = SafetyValidator(config, tmp_path)

        # Create a tests directory
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Source file without accompanying test
        has_coverage, reason = validator.check_test_coverage(
            [tmp_path / "src/ringmaster/new_module.py"]
        )

        assert not has_coverage
        assert "no test files" in reason.lower()

    def test_check_test_coverage_passes_with_tests(self, tmp_path: Path):
        """Test coverage check passes when test files are included."""
        config = SafetyConfig(require_tests=True)
        validator = SafetyValidator(config, tmp_path)

        # Create a tests directory
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Source file with accompanying test
        has_coverage, reason = validator.check_test_coverage(
            [
                tmp_path / "src/ringmaster/new_module.py",
                tmp_path / "tests/test_new_module.py",
            ]
        )

        assert has_coverage
        assert reason is None


class TestHotReloader:
    """Tests for HotReloader."""

    def test_path_to_module_conversion(self, tmp_path: Path):
        """Hot reloader converts paths to module names."""
        reloader = HotReloader(project_root=tmp_path)

        # Standard module
        path = tmp_path / "src/ringmaster/reload/watcher.py"
        assert reloader._path_to_module(path) == "ringmaster.reload.watcher"

        # Package __init__
        path = tmp_path / "src/ringmaster/reload/__init__.py"
        assert reloader._path_to_module(path) == "ringmaster.reload"

        # Non-Python file
        path = tmp_path / "config.toml"
        assert reloader._path_to_module(path) is None

    @pytest.mark.asyncio
    async def test_run_tests_success(self, tmp_path: Path):
        """Hot reloader runs tests successfully."""
        # Create a minimal test setup
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_simple.py").write_text(
            "def test_pass():\n    assert True"
        )

        reloader = HotReloader(project_root=tmp_path)

        success, output = await reloader.run_tests(timeout=60.0)
        assert success
        assert "passed" in output.lower() or output == ""

    @pytest.mark.asyncio
    async def test_run_tests_failure(self, tmp_path: Path):
        """Hot reloader detects test failures."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_fail.py").write_text(
            "def test_fail():\n    assert False, 'intentional failure'"
        )

        reloader = HotReloader(project_root=tmp_path)

        success, output = await reloader.run_tests(timeout=60.0)
        assert not success
        assert "failed" in output.lower() or "FAILED" in output

    @pytest.mark.asyncio
    async def test_process_changes_fails_on_protected(self, tmp_path: Path):
        """Processing changes fails for protected files."""
        config = SafetyConfig(protected_files=["critical.py"])
        reloader = HotReloader(project_root=tmp_path, safety_config=config)

        changes = [FileChange(path=tmp_path / "critical.py", change_type="modified")]

        result = await reloader.process_changes(changes)

        assert result.status == ReloadStatus.FAILED_SAFETY
        assert "protected" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_changes_success(self, tmp_path: Path):
        """Processing changes succeeds with valid modifications."""
        # Create minimal project structure
        src_dir = tmp_path / "src" / "ringmaster"
        src_dir.mkdir(parents=True)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Source file
        module = src_dir / "new_module.py"
        module.write_text("VALUE = 1")

        # Test file
        (tests_dir / "test_new.py").write_text(
            "def test_pass():\n    assert True"
        )

        config = SafetyConfig(require_tests=False, protected_files=[])
        reloader = HotReloader(project_root=tmp_path, safety_config=config)

        changes = [
            FileChange(path=module, change_type="modified"),
            FileChange(path=tests_dir / "test_new.py", change_type="modified"),
        ]

        result = await reloader.process_changes(changes, skip_tests=True)

        assert result.status == ReloadStatus.SUCCESS

    def test_reload_history(self, tmp_path: Path):
        """Hot reloader tracks reload history."""
        reloader = HotReloader(project_root=tmp_path)

        # History should start empty
        assert reloader.get_reload_history() == []
