"""Platform-specific worker implementations."""

import asyncio
import logging
import os
import shutil
from pathlib import Path

from ringmaster.worker.interface import (
    SessionConfig,
    SessionHandle,
    WorkerInterface,
)

logger = logging.getLogger(__name__)


class ClaudeCodeWorker(WorkerInterface):
    """Worker implementation for Claude Code CLI."""

    def __init__(
        self,
        config_dir: Path | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self._config_dir = config_dir
        self._default_model = model

    @property
    def name(self) -> str:
        return "claude-code"

    async def is_available(self) -> bool:
        """Check if claude CLI is available."""
        return shutil.which("claude") is not None

    async def start_session(self, config: SessionConfig) -> SessionHandle:
        """Start a Claude Code session."""
        cmd = ["claude"]

        # Add model if specified
        model = config.model or self._default_model
        if model:
            cmd.extend(["--model", model])

        # Add prompt
        cmd.extend(["-p", config.prompt])

        # Add extra args
        cmd.extend(config.extra_args)

        # Build environment
        env = os.environ.copy()
        env.update(config.env_vars)

        # Set config directory if specified
        if self._config_dir:
            env["CLAUDE_CONFIG_DIR"] = str(self._config_dir)

        # Start process
        logger.info(f"Starting Claude Code in {config.working_dir}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config.working_dir,
            env=env,
        )

        return SessionHandle(process, config, self.name)


class AiderWorker(WorkerInterface):
    """Worker implementation for Aider CLI."""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
    ):
        self._default_model = model

    @property
    def name(self) -> str:
        return "aider"

    async def is_available(self) -> bool:
        """Check if aider CLI is available."""
        return shutil.which("aider") is not None

    async def start_session(self, config: SessionConfig) -> SessionHandle:
        """Start an Aider session."""
        cmd = ["aider"]

        # Add model if specified
        model = config.model or self._default_model
        if model:
            cmd.extend(["--model", model])

        # Aider uses --message for non-interactive prompts
        cmd.extend(["--message", config.prompt])

        # Add yes-always for non-interactive mode
        cmd.append("--yes-always")

        # Add extra args
        cmd.extend(config.extra_args)

        # Build environment
        env = os.environ.copy()
        env.update(config.env_vars)

        # Start process
        logger.info(f"Starting Aider in {config.working_dir}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config.working_dir,
            env=env,
        )

        return SessionHandle(process, config, self.name)


class GenericWorker(WorkerInterface):
    """Generic worker for arbitrary CLI tools."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        prompt_flag: str = "-p",
    ):
        self._name = name
        self._command = command
        self._args = args or []
        self._prompt_flag = prompt_flag

    @property
    def name(self) -> str:
        return self._name

    async def is_available(self) -> bool:
        """Check if the command is available."""
        return shutil.which(self._command) is not None

    async def start_session(self, config: SessionConfig) -> SessionHandle:
        """Start a generic CLI session."""
        cmd = [self._command, *self._args]

        # Add prompt with the configured flag
        if self._prompt_flag:
            cmd.extend([self._prompt_flag, config.prompt])

        # Add extra args
        cmd.extend(config.extra_args)

        # Build environment
        env = os.environ.copy()
        env.update(config.env_vars)

        # Start process
        logger.info(f"Starting {self._name} in {config.working_dir}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config.working_dir,
            env=env,
        )

        return SessionHandle(process, config, self.name)


# Worker registry
WORKER_REGISTRY: dict[str, type[WorkerInterface]] = {
    "claude-code": ClaudeCodeWorker,
    "aider": AiderWorker,
}


def get_worker(worker_type: str, **kwargs) -> WorkerInterface:
    """Get a worker instance by type.

    Args:
        worker_type: Type of worker (e.g., 'claude-code', 'aider').
        **kwargs: Additional arguments for the worker constructor.

    Returns:
        WorkerInterface instance.

    Raises:
        ValueError: If worker type is not registered.
    """
    if worker_type not in WORKER_REGISTRY:
        raise ValueError(f"Unknown worker type: {worker_type}")

    return WORKER_REGISTRY[worker_type](**kwargs)
