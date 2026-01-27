"""Self-updating launcher for Ringmaster.

This module provides functionality for Ringmaster to update itself from GitHub releases,
similar to tools like ccdash. It can:
- Check for updates on GitHub releases
- Download new versions
- Replace the current binary/executable
- Restart with the new version
"""

from ringmaster.updater.launcher import (
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

__all__ = [
    "SelfUpdateResult",
    "UpdateStatus",
    "ReleaseInfo",
    "get_current_version",
    "check_for_updates",
    "download_update",
    "apply_update",
    "restart_with_new_version",
    "update_and_restart",
    "rollback",
    "get_platform_asset_name",
]
