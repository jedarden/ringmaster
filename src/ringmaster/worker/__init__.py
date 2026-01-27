"""Worker abstraction for coding agents."""

from ringmaster.worker.executor import WorkerExecutor
from ringmaster.worker.interface import WorkerInterface
from ringmaster.worker.monitor import (
    DegradationSignals,
    LivenessStatus,
    RecoveryAction,
    WorkerMonitor,
    recommend_recovery,
)
from ringmaster.worker.platforms import AiderWorker, ClaudeCodeWorker
from ringmaster.worker.spawner import SpawnedWorker, SpawnStatus, WorkerSpawner

__all__ = [
    "WorkerInterface",
    "WorkerExecutor",
    "ClaudeCodeWorker",
    "AiderWorker",
    "WorkerMonitor",
    "LivenessStatus",
    "DegradationSignals",
    "RecoveryAction",
    "recommend_recovery",
    "WorkerSpawner",
    "SpawnedWorker",
    "SpawnStatus",
]
