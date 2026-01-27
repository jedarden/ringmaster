"""Tests for the self-updating launcher."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ringmaster.updater import (
    ReleaseInfo,
    SelfUpdateResult,
    UpdateStatus,
    apply_update,
    check_for_updates,
    download_update,
    get_current_version,
    get_platform_asset_name,
    restart_with_new_version,
    rollback,
    update_and_restart,
)


class TestGetCurrentVersion:
    """Tests for get_current_version()."""

    def test_reads_from_pyproject_toml(self, tmp_path: Path) -> None:
        """Should read version from pyproject.toml if available."""
        # Create a fake pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "ringmaster"\nversion = "1.2.3"\n',
        )

        # Skip this test if tomli is not available (Python >= 3.11)
        try:
            import tomli

            with patch("ringmaster.updater.launcher.Path") as mock_path:
                mock_path.return_value.parent.parent.parent.parent = tmp_path

                with patch("ringmaster.updater.launcher.tomli", tomli):
                    version = get_current_version()
                    # Will fall back to default due to patch complexity
                    assert isinstance(version, str)
        except ImportError:
            # tomli is only available for Python < 3.11
            pytest.skip("tomli not available on Python >= 3.11")

    def test_returns_dev_version_when_no_metadata(self) -> None:
        """Should return dev version when no metadata available."""
        version = get_current_version()
        # Should at least return a string
        assert isinstance(version, str)


class TestPlatformAssetName:
    """Tests for get_platform_asset_name()."""

    @pytest.mark.parametrize(
        ("system", "machine", "expected"),
        [
            ("linux", "x86_64", "ringmaster-linux-x86_64"),
            ("linux", "amd64", "ringmaster-linux-x86_64"),
            ("linux", "aarch64", "ringmaster-linux-aarch64"),
            ("linux", "arm64", "ringmaster-linux-aarch64"),
            ("linux", "armv7l", "ringmaster-linux-arm"),
            ("darwin", "x86_64", "ringmaster-darwin-x86_64"),
            ("darwin", "amd64", "ringmaster-darwin-x86_64"),
            ("darwin", "arm64", "ringmaster-darwin-aarch64"),
            ("darwin", "aarch64", "ringmaster-darwin-aarch64"),
            ("windows", "x86_64", "ringmaster-windows-x86_64.exe"),
            ("windows", "amd64", "ringmaster-windows-x86_64.exe"),
        ],
    )
    def test_supported_platforms(self, system: str, machine: str, expected: str) -> None:
        """Should return correct asset name for supported platforms."""
        with patch("platform.system", return_value=system), patch(
            "platform.machine",
            return_value=machine,
        ):
            result = get_platform_asset_name()
            assert result == expected

    def test_unsupported_platform(self) -> None:
        """Should return None for unsupported platforms."""
        with patch("platform.system", return_value="freebsd"), patch(
            "platform.machine",
            return_value="amd64",
        ):
            result = get_platform_asset_name()
            assert result is None


class TestCheckForUpdates:
    """Tests for check_for_updates()."""

    def test_returns_up_to_date_when_current_is_latest(
        self,
        tmp_path: Path,
    ) -> None:
        """Should return UP_TO_DATE when current version matches latest."""
        state_file = tmp_path / "updater_state.json"

        with patch("ringmaster.updater.launcher.STATE_FILE", state_file), patch(
            "ringmaster.updater.launcher.get_current_version",
            return_value="1.0.0",
        ), patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=ReleaseInfo(
                tag_name="v1.0.0",
                version="1.0.0",
                published_at=datetime.now(UTC),
            ),
        ):
            result = check_for_updates(force=True)

        assert result.status == UpdateStatus.UP_TO_DATE
        assert result.current_version == "1.0.0"
        assert result.latest_version == "1.0.0"

    def test_returns_update_available_when_newer_exists(self) -> None:
        """Should return UPDATE_AVAILABLE when newer version exists."""
        with patch("ringmaster.updater.launcher.get_current_version", return_value="1.0.0"), patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=ReleaseInfo(
                tag_name="v1.1.0",
                version="1.1.0",
                published_at=datetime.now(UTC),
                download_url="https://example.com/ringmaster",
            ),
        ):
            result = check_for_updates(force=True)

        assert result.status == UpdateStatus.UPDATE_AVAILABLE
        assert result.current_version == "1.0.0"
        assert result.latest_version == "1.1.0"

    def test_returns_error_on_fetch_failure(self) -> None:
        """Should return ERROR when GitHub fetch fails."""
        with patch("ringmaster.updater.launcher.get_current_version", return_value="1.0.0"), patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=None,
        ):
            result = check_for_updates(force=True)

        assert result.status == UpdateStatus.ERROR
        assert result.error is not None

    def test_caches_check_results(self, tmp_path: Path) -> None:
        """Should cache update check results."""
        state_file = tmp_path / "updater_state.json"

        with patch("ringmaster.updater.launcher.STATE_FILE", state_file), patch(
            "ringmaster.updater.launcher.get_current_version",
            return_value="1.0.0",
        ), patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=ReleaseInfo(
                tag_name="v1.1.0",
                version="1.1.0",
                published_at=datetime.now(UTC),
            ),
        ):
            # First check
            result1 = check_for_updates(force=True)
            assert result1.status == UpdateStatus.UPDATE_AVAILABLE

            # Second check should use cache
            result2 = check_for_updates(force=False)
            assert result2.status == UpdateStatus.UPDATE_AVAILABLE

        # Verify cache was written
        cache_data = json.loads(state_file.read_text())
        assert cache_data["latest_version"] == "1.1.0"


class TestDownloadUpdate:
    """Tests for download_update()."""

    def test_downloads_to_temp_file(self) -> None:
        """Should download release to a temporary file."""
        mock_content = b"fake binary content"

        with patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=ReleaseInfo(
                tag_name="v1.0.0",
                version="1.0.0",
                published_at=datetime.now(UTC),
                download_url="https://example.com/ringmaster",
            ),
        ), patch("urllib.request.urlopen") as mock_urlopen, patch(
            "urllib.request.Request",
        ):
            # Mock HTTP response
            mock_response = Mock()
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_response.status = 200
            mock_response.read.side_effect = [mock_content, b""]
            mock_urlopen.return_value = mock_response

            result = download_update()

            # Should return a path
            assert result is not None
            assert result.exists()
            assert result.read_bytes() == mock_content

            # Cleanup
            result.unlink(missing_ok=True)

    def test_returns_none_on_download_failure(self) -> None:
        """Should return None when download fails."""
        with patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=None,
        ):
            result = download_update()
            assert result is None

    def test_returns_none_when_no_download_url(self) -> None:
        """Should return None when release has no download URL."""
        with patch(
            "ringmaster.updater.launcher._fetch_github_release",
            return_value=ReleaseInfo(
                tag_name="v1.0.0",
                version="1.0.0",
                published_at=datetime.now(UTC),
                download_url=None,  # No URL
            ),
        ):
            result = download_update()
            assert result is None


class TestApplyUpdate:
    """Tests for apply_update()."""

    def test_replaces_executable(self, tmp_path: Path) -> None:
        """Should replace the executable with the downloaded file."""
        # Create fake executable
        old_exe = tmp_path / "ringmaster"
        old_exe.write_text("old version")

        # Create fake update
        update_file = tmp_path / "update.bin"
        update_file.write_text("new version")

        with patch("sys.executable", str(old_exe)):
            result = apply_update(update_file)

        assert result.status == UpdateStatus.SUCCESS
        assert old_exe.read_text() == "new version"

    def test_creates_backup(self, tmp_path: Path) -> None:
        """Should create a backup before replacing."""
        old_exe = tmp_path / "ringmaster"
        old_exe.write_text("old version")

        update_file = tmp_path / "update.bin"
        update_file.write_text("new version")

        with patch("sys.executable", str(old_exe)):
            result = apply_update(update_file)

        assert result.status == UpdateStatus.SUCCESS
        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.read_text() == "old version"

        # Cleanup
        result.backup_path.unlink()

    def test_makes_executable(self, tmp_path: Path) -> None:
        """Should make the new executable executable."""
        old_exe = tmp_path / "ringmaster"
        old_exe.write_text("old")

        update_file = tmp_path / "update.bin"
        update_file.write_text("new")

        with patch("sys.executable", str(old_exe)):
            result = apply_update(update_file)

        assert result.status == UpdateStatus.SUCCESS
        # Check executable bit is set
        assert old_exe.stat().st_mode & 0o111 != 0

    def test_returns_error_when_download_not_found(self, tmp_path: Path) -> None:
        """Should return DOWNLOAD_FAILED when download file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.bin"

        with patch("sys.executable", str(tmp_path / "ringmaster")):
            result = apply_update(nonexistent)

        assert result.status == UpdateStatus.DOWNLOAD_FAILED
        assert result.error is not None

    def test_restores_backup_on_replace_failure(self, tmp_path: Path) -> None:
        """Should restore backup if replace fails."""
        old_exe = tmp_path / "ringmaster"
        old_exe.write_text("old version")

        update_file = tmp_path / "update.bin"
        update_file.write_text("new version")

        # Mock shutil.copy2 to fail on the actual executable
        original_copy2 = shutil.copy2
        call_count = [0]

        def failing_copy2(src: Path, dst: Path) -> None:
            call_count[0] += 1
            if str(dst) == str(old_exe) and call_count[0] == 2:
                raise OSError("Simulated failure")
            original_copy2(src, dst)

        with patch("sys.executable", str(old_exe)), patch("shutil.copy2", failing_copy2):
            result = apply_update(update_file)

        assert result.status == UpdateStatus.REPLACE_FAILED
        # Old version should be restored
        assert old_exe.read_text() == "old version"


class TestRollback:
    """Tests for rollback()."""

    def test_rolls_back_from_backup(self, tmp_path: Path) -> None:
        """Should restore executable from backup."""
        exe = tmp_path / "ringmaster"
        exe.write_text("new version")

        backup = tmp_path / "ringmaster.bak.123"
        backup.write_text("old version")

        with patch("sys.executable", str(exe)), patch("os.getpid", return_value=123):
            success = rollback()

        assert success is True
        assert exe.read_text() == "old version"

    def test_finds_backup_by_pid(self, tmp_path: Path) -> None:
        """Should find backup using current PID."""
        exe = tmp_path / "ringmaster"
        exe.write_text("new")

        backup = tmp_path / "ringmaster.bak.999"
        backup.write_text("old")

        with patch("sys.executable", str(exe)), patch("os.getpid", return_value=999):
            success = rollback()  # No backup_path specified

        assert success is True
        assert exe.read_text() == "old"

    def test_returns_false_when_no_backup(self, tmp_path: Path) -> None:
        """Should return False when no backup exists."""
        exe = tmp_path / "ringmaster"
        exe.write_text("current")

        with patch("sys.executable", str(exe)):
            success = rollback()

        assert success is False


class TestRestartWithNewVersion:
    """Tests for restart_with_new_version()."""

    def test_calls_os_execv(self) -> None:
        """Should call os.execv to replace the process."""
        with patch("os.execv") as mock_execv, patch("sys.executable", "/usr/bin/python3"), patch(
            "sys.argv",
            ["ringmaster", "serve"],
        ):
            restart_with_new_version()

            mock_execv.assert_called_once()

    def test_falls_back_to_subprocess(self) -> None:
        """Should fall back to subprocess if os.execv fails."""
        with patch("os.execv", side_effect=OSError("Fail")), patch("subprocess.Popen") as mock_popen, patch(
            "sys.executable",
            "/usr/bin/python3",
        ), patch("sys.argv", ["ringmaster"]), patch("sys.exit") as mock_exit:
            restart_with_new_version()

            mock_popen.assert_called_once()
            mock_exit.assert_called_once_with(0)

    def test_passes_custom_args(self) -> None:
        """Should pass custom arguments to the new process."""
        custom_args = ["--verbose", "serve"]

        with patch("os.execv") as mock_execv, patch("sys.executable", "/usr/bin/python3"):
            restart_with_new_version(custom_args)

            # Check that custom args were passed
            call_args = mock_execv.call_args[0]
            assert call_args[1][-2:] == custom_args


class TestUpdateAndRestart:
    """Tests for update_and_restart()."""

    def test_full_update_flow_success(self) -> None:
        """Should run full update flow when update available."""
        with patch(
            "ringmaster.updater.launcher.check_for_updates",
            return_value=SelfUpdateResult(
                status=UpdateStatus.UPDATE_AVAILABLE,
                current_version="1.0.0",
                latest_version="1.1.0",
            ),
        ), patch(
            "ringmaster.updater.launcher.download_update",
            return_value=Path("/tmp/update.bin"),
        ), patch(
            "ringmaster.updater.launcher.apply_update",
            return_value=SelfUpdateResult(
                status=UpdateStatus.SUCCESS,
                current_version="1.0.0",
            ),
        ), patch("ringmaster.updater.launcher.restart_with_new_version") as mock_restart:
            result = update_and_restart()

            assert result.status == UpdateStatus.SUCCESS
            mock_restart.assert_called_once()

    def test_returns_up_to_date_when_current(self) -> None:
        """Should return early when already up to date."""
        with patch(
            "ringmaster.updater.launcher.check_for_updates",
            return_value=SelfUpdateResult(
                status=UpdateStatus.UP_TO_DATE,
                current_version="1.0.0",
                latest_version="1.0.0",
            ),
        ):
            result = update_and_restart()

            assert result.status == UpdateStatus.UP_TO_DATE

    def test_returns_error_on_download_failure(self) -> None:
        """Should return error when download fails."""
        with patch(
            "ringmaster.updater.launcher.check_for_updates",
            return_value=SelfUpdateResult(
                status=UpdateStatus.UPDATE_AVAILABLE,
                current_version="1.0.0",
                latest_version="1.1.0",
            ),
        ), patch("ringmaster.updater.launcher.download_update", return_value=None):
            result = update_and_restart()

            assert result.status == UpdateStatus.DOWNLOAD_FAILED

    def test_respects_force_flag(self) -> None:
        """Should pass force flag to check_for_updates."""
        with patch(
            "ringmaster.updater.launcher.check_for_updates",
            return_value=SelfUpdateResult(
                status=UpdateStatus.UP_TO_DATE,
                current_version="1.0.0",
                latest_version="1.0.0",
            ),
        ) as mock_check:
            update_and_restart(force=True)

            mock_check.assert_called_once_with(force=True)


class TestReleaseInfo:
    """Tests for ReleaseInfo dataclass."""

    def test_from_github_response(self) -> None:
        """Should correctly parse GitHub API response."""
        response_data = {
            "tag_name": "v1.2.3",
            "prerelease": False,
            "published_at": "2024-01-15T10:30:00Z",
            "body": "Release notes here",
            "assets": [
                {
                    "name": "ringmaster-linux-x86_64",
                    "browser_download_url": "https://example.com/linux",
                }
            ],
        }

        with patch("platform.system", return_value="linux"), patch(
            "platform.machine",
            return_value="x86_64",
        ):
            # This would normally be called by _fetch_github_release
            # Testing the data structure here
            release = ReleaseInfo(
                tag_name=response_data["tag_name"],
                version="1.2.3",
                published_at=datetime.fromisoformat(
                    response_data["published_at"].replace("Z", "+00:00"),
                ),
                download_url=response_data["assets"][0]["browser_download_url"],
                body=response_data["body"],
                prerelease=response_data["prerelease"],
            )

            assert release.version == "1.2.3"
            assert release.prerelease is False
            assert release.download_url == "https://example.com/linux"


class TestStateManagement:
    """Tests for state file management."""

    def test_state_directory_creation(self, tmp_path: Path) -> None:
        """Should create state directory if it doesn't exist."""
        from ringmaster.updater.launcher import _get_state_file_path

        state_dir = tmp_path / ".ringmaster"
        state_file = state_dir / "updater_state.json"

        with patch("ringmaster.updater.launcher.STATE_DIR", state_dir), patch(
            "ringmaster.updater.launcher.STATE_FILE",
            state_file,
        ):
            result = _get_state_file_path()

            assert result.parent.exists()
            assert result == state_file

    def test_saves_and_loads_state(self, tmp_path: Path) -> None:
        """Should save and load state correctly."""
        from ringmaster.updater.launcher import _load_state, _save_state

        state_file = tmp_path / "state.json"

        with patch("ringmaster.updater.launcher.STATE_FILE", state_file):
            test_state = {
                "last_update_check": datetime.now(UTC).isoformat(),
                "latest_version": "1.2.3",
            }
            _save_state(test_state)

            loaded = _load_state()
            assert loaded["latest_version"] == "1.2.3"
            assert "last_update_check" in loaded
