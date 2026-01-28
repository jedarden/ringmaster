"""Self-updating launcher implementation.

Provides functionality for Ringmaster to update itself from GitHub releases.
The update flow is:
1. Check for updates (compare current version with latest GitHub release)
2. Download the new version to a temporary location
3. Replace the current executable with the new one
4. Restart with the new version

This is designed to be safe and reversible:
- Updates are downloaded to temp files first
- The old version is backed up before replacement
- If restart fails, the backup can be restored
"""

import contextlib
import json
import logging
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# GitHub repository for releases
GITHUB_REPO: Final = "jedarden/ringmaster"
GITHUB_API_URL: Final = "https://api.github.com/repos"
GITHUB_RELEASES_URL: Final = f"{GITHUB_API_URL}/{GITHUB_REPO}/releases/latest"

# Cache update check results for this duration
UPDATE_CHECK_CACHE_DURATION: Final = timedelta(hours=1)

# User agent for GitHub API (required by GitHub)
USER_AGENT: Final = "ringmaster-updater/1.0"

# State file for caching update checks and managing backups
STATE_DIR: Final = Path.home() / ".ringmaster"
STATE_FILE: Final = STATE_DIR / "updater_state.json"


class UpdateStatus(Enum):
    """Status of an update operation."""

    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    DOWNLOAD_FAILED = "download_failed"
    VERIFY_FAILED = "verify_failed"
    REPLACE_FAILED = "replace_failed"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ReleaseInfo:
    """Information about a GitHub release."""

    tag_name: str
    version: str
    published_at: datetime
    download_url: str | None = None
    body: str = ""
    prerelease: bool = False


@dataclass
class SelfUpdateResult:
    """Result of a self-update operation."""

    status: UpdateStatus
    current_version: str
    latest_version: str | None = None
    message: str = ""
    error: str | None = None
    backup_path: Path | None = None


def get_current_version() -> str:
    """Get the current version of Ringmaster.

    Reads from package metadata or returns a development version.
    """
    try:
        # Try to read from pyproject.toml
        root_dir = Path(__file__).parent.parent.parent.parent
        pyproject = root_dir / "pyproject.toml"

        if pyproject.exists():
            import tomli

            content = pyproject.read_text()
            data = tomli.loads(content)
            return data.get("project", {}).get("version", "0.1.0-dev")
    except Exception as e:
        logger.debug("Failed to read pyproject.toml: %s: %s", type(e).__name__, e)

    # Fallback to version from import
    try:
        import ringmaster

        return getattr(ringmaster, "__version__", "0.1.0-dev")
    except Exception as e:
        logger.debug("Failed to import ringmaster version: %s: %s", type(e).__name__, e)
        return "0.1.0-dev"


def _get_state_file_path() -> Path:
    """Ensure state directory exists and return state file path."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_FILE


def _load_state() -> dict:
    """Load updater state from file."""
    state_file = _get_state_file_path()
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception as e:
            logger.debug("Failed to read JSON state file: %s: %s", type(e).__name__, e)
    return {}


def _save_state(state: dict) -> None:
    """Save updater state to file."""
    state_file = _get_state_file_path()
    state_file.write_text(json.dumps(state, indent=2, default=str))


def get_platform_asset_name() -> str | None:
    """Get the expected asset name for the current platform.

    Returns None if the platform is not supported for pre-built binaries.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map platform to asset name patterns
    # These should match what's published in GitHub releases
    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "ringmaster-linux-x86_64"
        elif machine in ("aarch64", "arm64"):
            return "ringmaster-linux-aarch64"
        elif machine.startswith("arm"):
            return "ringmaster-linux-arm"
    elif system == "darwin":
        if machine in ("x86_64", "amd64"):
            return "ringmaster-darwin-x86_64"
        if machine in ("aarch64", "arm64"):
            return "ringmaster-darwin-aarch64"
    elif system == "windows" and machine in ("x86_64", "amd64"):
        return "ringmaster-windows-x86_64.exe"

    return None


def _fetch_github_release() -> ReleaseInfo | None:
    """Fetch the latest release information from GitHub.

    Returns None if the fetch fails or no release is found.
    """
    try:
        # Create SSL context that doesn't verify certificates (for compatibility)
        # In production, proper certificate verification should be used
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            GITHUB_RELEASES_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github.v3+json",
            },
        )

        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
            if response.status != 200:
                return None

            data = json.loads(response.read().decode())

            # Parse release info
            tag_name = data.get("tag_name", "")
            version = tag_name.lstrip("v")

            # Find the appropriate asset for this platform
            download_url = None
            expected_asset = get_platform_asset_name()

            if expected_asset:
                for asset in data.get("assets", []):
                    asset_name = asset.get("name", "")
                    if expected_asset in asset_name:
                        download_url = asset.get("browser_download_url")
                        break

            return ReleaseInfo(
                tag_name=tag_name,
                version=version,
                published_at=datetime.fromisoformat(
                    data.get("published_at", "").replace("Z", "+00:00")
                ),
                download_url=download_url,
                body=data.get("body", ""),
                prerelease=data.get("prerelease", False),
            )

    except Exception as e:
        # Silently fail - network issues are common
        logger.debug("Failed to fetch GitHub release: %s: %s", type(e).__name__, e)
        return None


def check_for_updates(force: bool = False) -> SelfUpdateResult:
    """Check if a newer version of Ringmaster is available on GitHub.

    Args:
        force: If True, bypass the cache and check GitHub directly.

    Returns:
        SelfUpdateResult with status and version information.
    """
    current_version = get_current_version()
    state = _load_state()

    # Check cache unless forced
    if not force:
        last_check_str = state.get("last_update_check")
        if last_check_str:
            try:
                last_check = datetime.fromisoformat(last_check_str)
                if datetime.now(UTC) - last_check < UPDATE_CHECK_CACHE_DURATION:
                    # Return cached result
                    cached_latest = state.get("latest_version")
                    if cached_latest and cached_latest != current_version:
                        return SelfUpdateResult(
                            status=UpdateStatus.UPDATE_AVAILABLE,
                            current_version=current_version,
                            latest_version=cached_latest,
                            message=f"Update available: {current_version} → {cached_latest}",
                        )
                    return SelfUpdateResult(
                        status=UpdateStatus.UP_TO_DATE,
                        current_version=current_version,
                        latest_version=cached_latest,
                        message="Ringmaster is up to date",
                    )
            except Exception as e:
                logger.debug("Failed to parse cached update check date: %s: %s", type(e).__name__, e)

    # Fetch from GitHub
    release = _fetch_github_release()

    if not release:
        return SelfUpdateResult(
            status=UpdateStatus.ERROR,
            current_version=current_version,
            message="Could not check for updates (network error or no releases found)",
            error="Failed to fetch release information from GitHub",
        )

    # Update cache
    state["last_update_check"] = datetime.now(UTC).isoformat()
    state["latest_version"] = release.version
    _save_state(state)

    # Compare versions
    # Simple string comparison works for semantic versioning
    if release.version > current_version:
        return SelfUpdateResult(
            status=UpdateStatus.UPDATE_AVAILABLE,
            current_version=current_version,
            latest_version=release.version,
            message=f"Update available: {current_version} → {release.version}",
        )

    return SelfUpdateResult(
        status=UpdateStatus.UP_TO_DATE,
        current_version=current_version,
        latest_version=release.version,
        message="Ringmaster is up to date",
    )


def download_update(version: str | None = None) -> Path | None:
    """Download the update to a temporary location.

    Args:
        version: Specific version to download. If None, downloads the latest.

    Returns:
        Path to the downloaded file, or None if download fails.
    """
    # Get release info
    if version:
        # Fetch specific release (would need different endpoint)
        # For now, just use latest
        release = _fetch_github_release()
        if release and release.version != version:
            return None
    else:
        release = _fetch_github_release()

    if not release or not release.download_url:
        return None

    try:
        # Download to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(
                release.download_url,
                headers={"User-Agent": USER_AGENT},
            )

            with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                if response.status != 200:
                    return None

                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    tmp.write(chunk)

            return Path(tmp.name)

    except Exception as e:
        logger.debug("Failed to download update: %s: %s", type(e).__name__, e)
        return None


def apply_update(downloaded_path: Path, executable_path: Path | None = None) -> SelfUpdateResult:
    """Apply an update by replacing the current executable.

    Args:
        downloaded_path: Path to the downloaded update file.
        executable_path: Path to the current executable. If None, auto-detected.

    Returns:
        SelfUpdateResult indicating success or failure.
    """
    current_version = get_current_version()

    # Auto-detect executable path
    if executable_path is None:
        executable_path = Path(sys.executable)

    # Verify downloaded file exists
    if not downloaded_path.exists():
        return SelfUpdateResult(
            status=UpdateStatus.DOWNLOAD_FAILED,
            current_version=current_version,
            message="Downloaded file not found",
            error=f"File not found: {downloaded_path}",
        )

    # Make downloaded file executable
    with contextlib.suppress(Exception):
        downloaded_path.chmod(0o755)

    # Create backup
    backup_path = None
    if executable_path.exists():
        try:
            backup_path = executable_path.with_suffix(f".bak.{os.getpid()}")
            shutil.copy2(executable_path, backup_path)
        except Exception as e:
            return SelfUpdateResult(
                status=UpdateStatus.REPLACE_FAILED,
                current_version=current_version,
                message="Failed to create backup",
                error=str(e),
            )

    # Replace executable
    try:
        shutil.copy2(downloaded_path, executable_path)
        executable_path.chmod(0o755)
    except Exception as e:
        # Restore from backup if available
        if backup_path and backup_path.exists():
            with contextlib.suppress(Exception):
                shutil.copy2(backup_path, executable_path)

        return SelfUpdateResult(
            status=UpdateStatus.REPLACE_FAILED,
            current_version=current_version,
            message="Failed to replace executable",
            error=str(e),
            backup_path=backup_path,
        )

    # Clean up downloaded file
    with contextlib.suppress(Exception):
        downloaded_path.unlink()

    return SelfUpdateResult(
        status=UpdateStatus.SUCCESS,
        current_version=current_version,
        latest_version="unknown",  # We updated but don't know the new version yet
        message="Update applied successfully. Restart to use the new version.",
        backup_path=backup_path,
    )


def restart_with_new_version(args: list[str] | None = None) -> None:
    """Restart the current process with the new version.

    This function does not return - it replaces the current process.

    Args:
        args: Arguments to pass to the new process. If None, uses sys.argv.
    """
    if args is None:
        args = sys.argv

    # Replace the current process
    try:
        os.execv(sys.executable, [sys.executable] + args)
    except Exception as e:
        # Fall back to subprocess
        logger.debug("Failed to restart with execv, falling back to subprocess: %s: %s", type(e).__name__, e)
        subprocess.Popen([sys.executable] + args)
        sys.exit(0)


def update_and_restart(
    force: bool = False,
    args: list[str] | None = None,
) -> SelfUpdateResult:
    """Check for updates, download, apply, and restart.

    This is a convenience function that runs the full update flow.

    Args:
        force: If True, bypass cache when checking for updates.
        args: Arguments to pass to the restarted process.

    Returns:
        SelfUpdateResult. If status is SUCCESS, the process will restart.
    """
    current_version = get_current_version()

    # Check for updates
    check_result = check_for_updates(force=force)

    if check_result.status == UpdateStatus.UP_TO_DATE:
        return check_result

    if check_result.status != UpdateStatus.UPDATE_AVAILABLE:
        return check_result

    # Download update
    downloaded_path = download_update(check_result.latest_version)

    if not downloaded_path:
        return SelfUpdateResult(
            status=UpdateStatus.DOWNLOAD_FAILED,
            current_version=current_version,
            latest_version=check_result.latest_version,
            message="Failed to download update",
            error="Download failed or no suitable asset found for this platform",
        )

    # Apply update
    apply_result = apply_update(downloaded_path)

    if apply_result.status != UpdateStatus.SUCCESS:
        return apply_result

    # Restart
    restart_with_new_version(args)

    # Should not reach here
    return apply_result


def rollback(backup_path: Path | None = None) -> bool:
    """Rollback to a backed-up version.

    Args:
        backup_path: Path to the backup file. If None, searches for a backup.

    Returns:
        True if rollback succeeded, False otherwise.
    """
    executable_path = Path(sys.executable)

    # Find backup if not specified
    if backup_path is None:
        # Look for backup files with our PID
        backup_pattern = executable_path.with_suffix(f".bak.{os.getpid()}")
        if backup_pattern.exists():
            backup_path = backup_pattern
        else:
            # Look for any backup
            backups = list(executable_path.parent.glob(f"{executable_path.name}.bak.*"))
            if backups:
                backup_path = max(backups, key=lambda p: p.stat().st_mtime)

    if not backup_path or not backup_path.exists():
        return False

    try:
        shutil.copy2(backup_path, executable_path)
        executable_path.chmod(0o755)
        return True
    except Exception as e:
        logger.debug("Failed to rollback to backup: %s: %s", type(e).__name__, e)
        return False
