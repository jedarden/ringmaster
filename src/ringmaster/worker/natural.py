"""Natural language worker configuration.

Simplified worker configuration with just:
- name
- description (optional)
- model (optional)
- start_script (with {prompt} placeholder)

Example:
    Claude Code with sonnet:
        name: "claude-code"
        description: "Anthropic's Claude Code CLI"
        model: "claude-sonnet-4-20250514"
        start_script: "claude --model {model} --print -- {prompt}"

    When executed with prompt="fix the bug":
        claude --model claude-sonnet-4-20250514 --print -- fix the bug
"""

import logging
import re
import shutil
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================

@dataclass
class WorkerDefinition:
    """Definition of a worker.

    A worker is simply a named script template that can be executed
    with a prompt injected into it.

    Attributes:
        name: Unique identifier for this worker
        description: Human-readable description (optional)
        model: Default model to use (optional)
        start_script: Shell script with {model} and {prompt} placeholders
    """

    name: str
    start_script: str
    description: str | None = None
    model: str | None = None

    def build_command(self, model: str | None = None, prompt: str = "") -> list[str]:
        """Build the command list for execution.

        Args:
            model: Override model (uses self.model if None)
            prompt: The prompt to inject

        Returns:
            List of command arguments for subprocess execution.
        """
        model = model or self.model
        script = self.start_script

        # Replace model placeholder
        if model:
            script = script.replace("{model}", model)

        # Replace prompt placeholder
        script = script.replace("{prompt}", prompt)

        # Parse into command list (simple shell-like parsing)
        # For now, just split on spaces - can be improved if needed
        import shlex
        return shlex.split(script)

    def is_available(self) -> bool:
        """Check if this worker's command is available."""
        # Extract the command name (first word of script)
        cmd = self.start_script.split()[0]
        return shutil.which(cmd) is not None


class WorkerConfig(BaseModel):
    """Configuration extracted from natural language."""

    success: bool
    name: str | None = None
    description: str | None = None
    model: str | None = None
    start_script: str | None = None
    error: str | None = None
    confidence: float = 0.0
    suggestions: list[str] = field(default_factory=list)


# =============================================================================
# Worker Registry
# =============================================================================

class WorkerRegistry:
    """Registry of available worker definitions."""

    def __init__(self):
        self._workers: dict[str, WorkerDefinition] = {}
        self._load_default_workers()

    def _load_default_workers(self):
        """Load default worker definitions."""
        default_workers = [
            WorkerDefinition(
                name="claude-code",
                description="Anthropic's Claude Code CLI",
                model="claude-sonnet-4-20250514",
                start_script="claude --model {model} --print -- {prompt}",
            ),
            WorkerDefinition(
                name="aider",
                description="Aider AI coding assistant",
                model="claude-3-5-sonnet-20241022",
                start_script="aider --model {model} --message {prompt} --yes",
            ),
            WorkerDefinition(
                name="cursor",
                description="Cursor AI coding assistant (CLI mode)",
                model="gpt-4o",
                start_script="cursor --model {model} --message {prompt}",
            ),
            WorkerDefinition(
                name="opencode",
                description="OpenCode AI coding assistant",
                model="gpt-4o",
                start_script="opencode --model {model} --prompt {prompt}",
            ),
            WorkerDefinition(
                name="codex",
                description="Codex CLI coding assistant",
                model="gpt-4o",
                start_script="codex --model {model} --message {prompt}",
            ),
            WorkerDefinition(
                name="goose",
                description="Goose AI coding assistant",
                model="gpt-4o",
                start_script="goose --model {model} {prompt}",
            ),
            WorkerDefinition(
                name="kilo",
                description="Kilo AI coding assistant",
                model="gpt-4o",
                start_script="kilo --model {model} {prompt}",
            ),
        ]
        for worker in default_workers:
            self._workers[worker.name] = worker

    def register(self, worker: WorkerDefinition):
        """Register a new worker."""
        self._workers[worker.name] = worker
        logger.info(f"Registered worker: {worker.name}")

    def get(self, name: str) -> WorkerDefinition | None:
        """Get worker by name."""
        return self._workers.get(name)

    def list_available(self) -> list[WorkerDefinition]:
        """List all available workers."""
        return [w for w in self._workers.values() if w.is_available()]

    def list_all(self) -> list[WorkerDefinition]:
        """List all registered workers."""
        return list(self._workers.values())


# =============================================================================
# Natural Language Parser
# =============================================================================

class NaturalWorkerParser:
    """Parse natural language into worker configuration."""

    # Worker name patterns
    WORKER_PATTERNS = [
        (r"\bclaude\s*code\b", "claude-code"),
        (r"\bclaude\s*cli\b", "claude-code"),
        (r"\baider\b", "aider"),
        (r"\bcursor\b", "cursor"),
        (r"\bopencode\b", "opencode"),
        (r"\bcodex\s*cli\b", "codex"),
        (r"\bgoose\b", "goose"),
        (r"\bkilo\s*code\b", "kilo"),
        (r"\bclaude\b(?!\s*3)(?!-3)", "claude-code"),
    ]

    # Model patterns
    MODEL_PATTERNS = [
        # Claude models (most specific first)
        (r"\b3\.5[- ]?sonnet\b|\bsonnet[- ]?3\.5\b", "claude-3-5-sonnet-20241022"),
        (r"\bopus[- ]?4\b", "claude-opus-4-20250514"),
        (r"\bsonnet[- ]?4\b", "claude-sonnet-4-20250514"),
        (r"\bsonnet\b", "claude-sonnet-4-20250514"),
        (r"\bhaiku\b", "claude-3-5-haiku-20241022"),
        (r"\bopus\b", "claude-opus-4-20250514"),
        # Other models
        (r"\bgpt[- ]?4o\b", "gpt-4o"),
        (r"\bgpt[- ]?4[- ]?turbo\b", "gpt-4-turbo"),
    ]

    def __init__(self, registry: WorkerRegistry):
        self.registry = registry

    def parse(self, description: str) -> WorkerConfig:
        """Parse natural language description into worker config.

        Args:
            description: Natural language like "claude code with sonnet"

        Returns:
            WorkerConfig with extracted configuration.
        """
        desc_lower = description.lower()
        result = WorkerConfig(success=False, confidence=0.0)

        # Extract worker name
        worker_name = self._extract_worker_name(desc_lower)
        if not worker_name:
            result.error = (
                "Could not identify worker. "
                "Try: claude-code, aider, cursor, opencode, codex, goose, kilo"
            )
            return result

        result.name = worker_name
        result.confidence += 0.4

        # Get worker definition
        worker_def = self.registry.get(worker_name)
        if worker_def:
            result.description = worker_def.description
            result.start_script = worker_def.start_script

        # Extract model
        model = self._extract_model(desc_lower)
        if model:
            result.model = model
            result.confidence += 0.4
        elif worker_def and worker_def.model:
            result.model = worker_def.model

        result.success = True
        result.confidence = min(result.confidence, 1.0)

        # Add suggestions if model wasn't explicitly mentioned
        if not model and worker_def:
            result.suggestions.append(f"Using default model: {worker_def.model}")

        return result

    def _extract_worker_name(self, description: str) -> str | None:
        """Extract worker name from description."""
        for pattern, name in self.WORKER_PATTERNS:
            if re.search(pattern, description):
                logger.debug(f"Matched worker: {name}")
                return name
        return None

    def _extract_model(self, description: str) -> str | None:
        """Extract model from description."""
        for pattern, model in self.MODEL_PATTERNS:
            if re.search(pattern, description):
                logger.debug(f"Matched model: {model}")
                return model
        return None


# =============================================================================
# Convenience Functions
# =============================================================================

_registry = WorkerRegistry()
_parser = NaturalWorkerParser(_registry)


def parse_worker_description(description: str) -> WorkerConfig:
    """Parse natural language worker description.

    Args:
        description: Natural language like "claude code with sonnet"

    Returns:
        WorkerConfig with extracted configuration.

    Example:
        >>> result = parse_worker_description("claude code with opus")
        >>> result.name  # "claude-code"
        >>> result.model  # "claude-opus-4-20250514"
        >>> result.start_script  # "claude --model {model} --print -- {prompt}"
    """
    return _parser.parse(description)


def create_worker(description: str) -> WorkerDefinition:
    """Create a worker from natural language description.

    Args:
        description: Natural language like "claude code with sonnet"

    Returns:
        WorkerDefinition ready for use.

    Raises:
        ValueError: If description cannot be parsed.

    Example:
        >>> worker = create_worker("claude code with opus")
        >>> worker.name  # "claude-code"
        >>> worker.model  # "claude-opus-4-20250514"
        >>> cmd = worker.build_command(prompt="fix the bug")
        >>> # ["claude", "--model", "claude-opus-4-20250514", "--print", "--", "fix", "the", "bug"]
    """
    config = parse_worker_description(description)

    if not config.success:
        raise ValueError(f"Could not parse worker description: {config.error}")

    return WorkerDefinition(
        name=config.name or "worker",
        description=config.description,
        model=config.model,
        start_script=config.start_script or "{prompt}",
    )


def list_workers() -> list[WorkerDefinition]:
    """List all available workers.

    Returns:
        List of WorkerDefinition for workers that are installed.
    """
    return _registry.list_available()


def list_all_workers() -> list[WorkerDefinition]:
    """List all registered workers (available or not).

    Returns:
        List of all WorkerDefinition.
    """
    return _registry.list_all()


def get_worker(name: str) -> WorkerDefinition | None:
    """Get worker by name.

    Args:
        name: Worker name (e.g., "claude-code")

    Returns:
        WorkerDefinition or None if not found.
    """
    return _registry.get(name)


def register_worker(worker: WorkerDefinition) -> None:
    """Register a new worker.

    Args:
        worker: WorkerDefinition to register.
    """
    _registry.register(worker)


__all__ = [
    "WorkerDefinition",
    "WorkerConfig",
    "WorkerRegistry",
    "NaturalWorkerParser",
    "parse_worker_description",
    "create_worker",
    "list_workers",
    "list_all_workers",
    "get_worker",
    "register_worker",
]
