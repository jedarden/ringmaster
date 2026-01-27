"""End-to-end tests for actual hot-reload self-improvement.

This test validates that when ringmaster modifies its own source code:
1. The file change is detected
2. Tests are run
3. Modules are reloaded in memory
4. New behavior takes effect immediately
5. Failed tests trigger rollback

This is the critical validation that the self-improvement flywheel actually works.
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

from ringmaster.reload.reloader import HotReloader, ReloadStatus
from ringmaster.reload.safety import SafetyConfig
from ringmaster.reload.watcher import FileChange, FileChangeWatcher


@pytest.fixture
def reload_project(tmp_path: Path):
    """Create a project structure for testing actual module reloading."""
    # Create source directory structure
    src_dir = tmp_path / "src" / "reloadtest"
    src_dir.mkdir(parents=True)

    # Create a module with an updatable value
    module_file = src_dir / "behaviors.py"
    module_file.write_text(
        '''"""Module with updatable behaviors for hot-reload testing."""

# This value will be modified to test reloading
COUNTER = 0

def get_counter() -> int:
    """Return the current counter value."""
    return COUNTER

def increment_counter() -> int:
    """Increment and return the counter."""
    global COUNTER
    COUNTER += 1
    return COUNTER

VERSION = "1.0.0"

def get_version() -> str:
    """Return the current version."""
    return VERSION
'''
    )

    # Create __init__.py
    init_file = src_dir / "__init__.py"
    init_file.write_text(
        '''"""Test module package."""

from reloadtest.behaviors import get_counter, increment_counter, get_version

__all__ = ["get_counter", "increment_counter", "get_version"]
'''
    )

    # Create test directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    # Create test file that doesn't import the module (to avoid import errors)
    test_file = tests_dir / "test_simple.py"
    test_file.write_text(
        '''"""Simple tests that always pass."""

def test_one():
    """Simple test."""
    assert True

def test_two():
    """Another simple test."""
    assert 1 + 1 == 2
'''
    )

    # Create pyproject.toml for pytest discovery
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '''[project]
name = "hot-reload-test"
version = "0.1.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = "src"
'''
    )

    return {
        "root": tmp_path,
        "src_dir": src_dir,
        "module_file": module_file,
        "init_file": init_file,
        "tests_dir": tests_dir,
        "test_file": test_file,
        "module_name": "reloadtest.behaviors",
        "package_name": "reloadtest",
    }


class TestModuleReloading:
    """Tests that verify actual Python module reloading."""

    @pytest.mark.asyncio
    async def test_module_is_actually_reloaded_in_memory(self, reload_project):
        """Verify that reload_module actually updates the module in memory."""
        project = reload_project
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Add src to path so we can import
        sys.path.insert(0, str(import_root))

        try:
            # Import the module
            import reloadtest.behaviors as behaviors

            # Get original value
            original_version = behaviors.get_version()
            assert original_version == "1.0.0", f"Expected 1.0.0, got {original_version}"

            # Modify the file
            project["module_file"].write_text(
                '''"""Module with updatable behaviors for hot-reload testing."""

# This value will be modified to test reloading
COUNTER = 0

def get_counter() -> int:
    """Return the current counter value."""
    return COUNTER

def increment_counter() -> int:
    """Increment and return the counter."""
    global COUNTER
    COUNTER += 1
    return COUNTER

VERSION = "2.5.0"

def get_version() -> str:
    """Return the current version."""
    return VERSION

def new_function() -> str:
    """A new function added after reload."""
    return "I am new!"
'''
            )

            # Create reloader
            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Reload the module
            success = reloader.reload_module("reloadtest.behaviors")
            assert success, "Module reload should succeed"

            # Verify the value changed in memory
            new_version = behaviors.get_version()
            assert new_version == "2.5.0", \
                f"Expected version to change to 2.5.0, but got {new_version}. " \
                f"Module was NOT reloaded in memory!"

            # Verify new function is available
            assert hasattr(behaviors, "new_function"), \
                "New function should be available after reload"
            assert behaviors.new_function() == "I am new!"

        finally:
            # Clean up sys.path
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            # Remove imported module
            if "reloadtest.behaviors" in sys.modules:
                del sys.modules["reloadtest.behaviors"]
            if "reloadtest" in sys.modules:
                del sys.modules["reloadtest"]

    @pytest.mark.asyncio
    async def test_hot_reload_workflow_end_to_end(self, reload_project):
        """Complete hot-reload workflow: change -> detect -> test -> reload."""
        project = reload_project
        module_file = project["module_file"]
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Add src to path
        sys.path.insert(0, str(import_root))

        try:
            import reloadtest.behaviors as behaviors

            # Verify initial state
            assert behaviors.get_version() == "1.0.0"

            # Initialize file watcher
            watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
            watcher.initialize()

            # Create reloader
            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
                auto_rollback=False,  # No git in temp directory
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Modify the source file
            module_file.write_text(
                '''"""Updated module."""

VERSION = "3.0.0"

def get_version() -> str:
    """Return the current version."""
    return VERSION
'''
            )

            # Wait a moment for file system to flush
            time.sleep(0.1)

            # Detect changes
            changes = watcher.detect_changes()
            assert len(changes) == 1, f"Should detect one file change, got {len(changes)}"
            assert changes[0].change_type == "modified"

            # Process changes (run tests + reload)
            result = await reloader.process_changes(
                changes,
                skip_tests=False,  # Run tests to validate
            )

            # Should succeed
            assert result.status == ReloadStatus.SUCCESS, \
                f"Reload failed: {result.error_message}"
            assert "reloadtest.behaviors" in result.reloaded_modules

            # Verify the module was reloaded in memory
            new_version = behaviors.get_version()
            assert new_version == "3.0.0", \
                f"Module was not reloaded! Still has version {new_version}"

        finally:
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            for mod in list(sys.modules.keys()):
                if mod.startswith("reloadtest"):
                    del sys.modules[mod]

    @pytest.mark.asyncio
    async def test_failing_tests_block_reload(self, reload_project):
        """Verify that failing tests prevent reload."""
        project = reload_project
        test_file = project["test_file"]
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Add src to path
        sys.path.insert(0, str(import_root))

        try:
            import reloadtest.behaviors as behaviors

            original_version = behaviors.get_version()
            assert original_version == "1.0.0"

            # Initialize watcher BEFORE making changes
            watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
            watcher.initialize()

            # Initialize reloader
            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
                auto_rollback=False,
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Modify source file
            project["module_file"].write_text(
                '''"""Modified module."""

VERSION = "99.0.0"

def get_version() -> str:
    return VERSION
'''
            )

            # Wait for file system
            time.sleep(0.1)

            # Detect source file change
            changes = watcher.detect_changes()
            assert len(changes) >= 1, f"Should detect at least one change, got {len(changes)}"

            # Now modify test to fail
            test_file.write_text(
                '''"""Test that will fail."""

def test_will_fail():
    """This test intentionally fails."""
    assert False, "Intentional failure"
'''
            )

            # Process changes - should fail due to test failure
            result = await reloader.process_changes(
                changes,
                skip_tests=False,  # Run tests
            )

            # Should fail
            assert result.status == ReloadStatus.FAILED_TESTS, \
                f"Expected FAILED_TESTS, got {result.status}"

            # Verify module was NOT reloaded
            current_version = behaviors.get_version()
            assert current_version == "1.0.0", \
                f"Module should not have been reloaded! Got version {current_version}"

        finally:
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            for mod in list(sys.modules.keys()):
                if mod.startswith("reloadtest"):
                    del sys.modules[mod]

    @pytest.mark.asyncio
    async def test_multiple_modules_reloaded_together(self, reload_project):
        """Verify that multiple related modules are all reloaded."""
        project = reload_project
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Add another module that depends on behaviors
        utils_file = src_dir / "utils.py"
        utils_file.write_text(
            '''"""Utility module."""

from reloadtest.behaviors import get_version

def get_full_version() -> str:
    """Get full version string."""
    return f"reloadtest v{get_version()}"
'''
        )

        # Update __init__.py to export utils
        project["init_file"].write_text(
            '''"""Test module package."""

from reloadtest.behaviors import get_counter, increment_counter, get_version
from reloadtest.utils import get_full_version

__all__ = ["get_counter", "increment_counter", "get_version", "get_full_version"]
'''
        )

        # Add src to path
        sys.path.insert(0, str(import_root))

        try:
            import reloadtest.behaviors as behaviors
            import reloadtest.utils as utils

            # Initial state
            assert behaviors.get_version() == "1.0.0"
            assert "v1.0.0" in utils.get_full_version()

            # Initialize watcher and reloader
            watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
            watcher.initialize()

            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Modify both files
            project["module_file"].write_text(
                '''"""Updated behaviors."""

VERSION = "4.0.0"

def get_version() -> str:
    return VERSION
'''
            )

            utils_file.write_text(
                '''"""Updated utility module."""

from reloadtest.behaviors import get_version

def get_full_version() -> str:
    """Get full version string."""
    return f"ReloadTest version {get_version()}"
'''
            )

            # Wait for file system
            time.sleep(0.1)

            # Detect and process changes
            changes = watcher.detect_changes()
            result = await reloader.process_changes(changes, skip_tests=True)

            assert result.status == ReloadStatus.SUCCESS
            assert "reloadtest.behaviors" in result.reloaded_modules
            assert "reloadtest.utils" in result.reloaded_modules

            # Verify both modules were reloaded
            assert behaviors.get_version() == "4.0.0"
            assert "version 4.0.0" in utils.get_full_version()

        finally:
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            for mod in list(sys.modules.keys()):
                if mod.startswith("reloadtest"):
                    del sys.modules[mod]

    @pytest.mark.asyncio
    async def test_package_init_reloaded(self, reload_project):
        """Verify that package __init__.py is also reloaded."""
        project = reload_project
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Add src to path
        sys.path.insert(0, str(import_root))

        try:
            import reloadtest

            # Initial state - get_version should be available
            assert hasattr(reloadtest, "get_version")
            assert reloadtest.get_version() == "1.0.0"

            # Initialize watcher and reloader
            watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
            watcher.initialize()

            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Modify __init__.py
            project["init_file"].write_text(
                '''"""Updated test module package."""

from reloadtest.behaviors import get_counter, increment_counter, get_version

# Add a new package-level variable
PACKAGE_NAME = "ReloadTest"

__all__ = ["get_counter", "increment_counter", "get_version", "PACKAGE_NAME"]
'''
            )

            # Wait for file system
            time.sleep(0.1)

            # Detect and process changes
            changes = watcher.detect_changes()
            result = await reloader.process_changes(changes, skip_tests=True)

            assert result.status == ReloadStatus.SUCCESS
            assert "reloadtest" in result.reloaded_modules

            # Verify package was reloaded
            assert hasattr(reloadtest, "PACKAGE_NAME")
            assert reloadtest.PACKAGE_NAME == "ReloadTest"

        finally:
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            for mod in list(sys.modules.keys()):
                if mod.startswith("reloadtest"):
                    del sys.modules[mod]


class TestHotReloadSafety:
    """Tests for hot-reload safety mechanisms."""

    @pytest.mark.asyncio
    async def test_protected_file_cannot_be_reloaded(self, reload_project):
        """Protected files cannot be hot-reloaded."""
        project = reload_project
        src_dir = project["src_dir"]

        # Configure module as protected
        safety_config = SafetyConfig(
            protected_files=["src/reloadtest/behaviors.py"],
            require_tests=False,
        )

        reloader = HotReloader(
            project_root=project["root"],
            safety_config=safety_config,
        )

        watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
        watcher.initialize()

        # Modify the protected file
        project["module_file"].write_text("# Protected modification\nVERSION = 'X.X.X'")

        # Wait for file system
        time.sleep(0.1)

        # Detect changes
        changes = watcher.detect_changes()
        assert len(changes) == 1

        # Process should fail on safety check
        result = await reloader.process_changes(changes)
        assert result.status == ReloadStatus.FAILED_SAFETY
        assert "protected" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_deleted_file_handling(self, reload_project):
        """Deleted files are handled gracefully."""
        project = reload_project
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Add src to path
        sys.path.insert(0, str(import_root))

        try:
            import reloadtest.behaviors as behaviors

            # Verify module exists
            assert hasattr(behaviors, "get_version")

            # Initialize watcher and reloader
            watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
            watcher.initialize()

            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Delete the file
            project["module_file"].unlink()

            # Wait for file system
            time.sleep(0.1)

            # Detect changes
            changes = watcher.detect_changes()
            assert len(changes) == 1, f"Should detect deletion, got {len(changes)} changes"
            assert changes[0].change_type == "deleted"

            # Process changes - deleted files can't be reloaded
            result = await reloader.process_changes(changes, skip_tests=True)

            # Should succeed but no modules reloaded
            assert result.status == ReloadStatus.SUCCESS
            assert len(result.reloaded_modules) == 0

        finally:
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            for mod in list(sys.modules.keys()):
                if mod.startswith("reloadtest"):
                    del sys.modules[mod]


class TestRingmasterSelfImprovement:
    """Tests that simulate ringmaster improving itself."""

    @pytest.mark.asyncio
    async def test_ringmaster_can_reload_its_own_modules(self, reload_project):
        """Verify that ringmaster can reload its own source code modules."""
        project = reload_project
        src_dir = project["src_dir"]
        import_root = project["root"] / "src"

        # Simulate ringmaster importing and using its own modules
        sys.path.insert(0, str(import_root))

        try:
            import reloadtest.behaviors as behaviors

            # Module is working with original code
            assert behaviors.get_version() == "1.0.0"

            # Initialize file watcher (as ringmaster would)
            watcher = FileChangeWatcher([src_dir], patterns=["*.py"])
            watcher.initialize()

            # Create hot reloader (as ringmaster would)
            safety_config = SafetyConfig(
                protected_files=[],
                require_tests=False,
            )
            reloader = HotReloader(
                project_root=project["root"],
                safety_config=safety_config,
            )

            # Simulate a task that modifies the source code
            # (e.g., "Update version to 5.0.0")
            project["module_file"].write_text(
                '''"""Improved module."""

VERSION = "5.0.0"

def get_version() -> str:
    """Return the current version."""
    return VERSION

def improved_feature() -> str:
    """A new feature added by self-improvement."""
    return "Self-improvement works!"
'''
            )

            # Wait for file system
            time.sleep(0.1)

            # Detect the change
            changes = watcher.detect_changes()
            assert len(changes) == 1, f"Should detect change, got {len(changes)}"

            # Process the change (run tests + reload)
            result = await reloader.process_changes(changes, skip_tests=False)

            # Should succeed
            assert result.status == ReloadStatus.SUCCESS
            assert "reloadtest.behaviors" in result.reloaded_modules

            # Verify the new code is now active in memory
            assert behaviors.get_version() == "5.0.0"
            assert behaviors.improved_feature() == "Self-improvement works!"

            # This proves the self-improvement flywheel works:
            # 1. Source code was modified
            # 2. Changes were detected
            # 3. Tests passed
            # 4. Module was reloaded in memory
            # 5. New behavior is immediately available

        finally:
            if str(import_root) in sys.path:
                sys.path.remove(str(import_root))
            for mod in list(sys.modules.keys()):
                if mod.startswith("reloadtest"):
                    del sys.modules[mod]
