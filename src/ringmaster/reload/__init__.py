"""Hot-reload support for self-improvement flywheel.

Based on docs/06-deployment.md:
- File watching for code changes
- Automatic test validation
- Component hot-reload
- Safety rails and rollback
"""

from ringmaster.reload.reloader import HotReloader, ReloadResult
from ringmaster.reload.safety import ProtectedFileError, SafetyValidator
from ringmaster.reload.watcher import ConfigWatcher, FileChangeWatcher

__all__ = [
    "ConfigWatcher",
    "FileChangeWatcher",
    "HotReloader",
    "ReloadResult",
    "SafetyValidator",
    "ProtectedFileError",
]
