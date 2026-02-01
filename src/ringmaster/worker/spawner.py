"""Worker spawner for tmux-based worker management.

Based on docs/09-remaining-decisions.md Section 4:
- On-demand spawning into tmux instances
- Bash script with while loop wrapping headless CLI
- Workers poll for beads via ringmaster CLI
"""

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SpawnStatus(str, Enum):
    """Status of a spawned worker."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class SpawnedWorker:
    """Represents a spawned worker in a tmux session."""

    worker_id: str
    worker_type: str
    tmux_session: str
    worktree_path: str | None
    log_path: str | None
    status: SpawnStatus = SpawnStatus.STARTING
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    pid: int | None = None


class WorkerSpawner:
    """Manages spawning workers in tmux sessions.

    Simplified approach: Workers run as LLM-generated bash scripts that:
    1. Poll for available beads via `ringmaster pull-bead`
    2. Build enriched prompts via `ringmaster build-prompt`
    3. Execute the CLI tool (claude, aider, codex, etc.)
    4. Report results via `ringmaster report-result`

    The generated_script field contains the complete worker logic.
    """

    # Default worker script template (used when no generated_script is provided)
    WORKER_SCRIPT_TEMPLATE = '''#!/bin/bash
# Ringmaster worker script for {worker_name}
# Auto-generated template (consider using LLM-generated script for customization)

set -euo pipefail

WORKER_ID="{worker_id}"
WORKER_NAME="{worker_name}"
WORKER_TYPE="{worker_type}"
LOG_FILE="{log_path}"
CAPABILITIES="{capabilities}"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}}

log "Worker $WORKER_NAME ($WORKER_TYPE) starting"
log "Capabilities: $CAPABILITIES"

# Signal handling
trap 'log "Received signal, shutting down..."; exit 0' SIGINT SIGTERM

# Main worker loop
ITERATION=0
BACKOFF=1
MAX_BACKOFF=60

while true; do
    # Pull next available bead
    CAP_ARGS=""
    if [ -n "$CAPABILITIES" ]; then
        for cap in $(echo "$CAPABILITIES" | tr ',' ' '); do
            CAP_ARGS="$CAP_ARGS -c $cap"
        done
    fi

    BEAD_JSON=$(ringmaster pull-bead "$WORKER_ID" $CAP_ARGS --json 2>/dev/null || echo "")

    if [ -z "$BEAD_JSON" ] || [ "$BEAD_JSON" = "null" ]; then
        # No work available, backoff
        sleep $BACKOFF
        BACKOFF=$((BACKOFF * 2))
        if [ $BACKOFF -gt $MAX_BACKOFF ]; then
            BACKOFF=$MAX_BACKOFF
        fi
        continue
    fi

    # Reset backoff on successful pull
    BACKOFF=1

    BEAD_ID=$(echo "$BEAD_JSON" | jq -r '.id')
    BEAD_TITLE=$(echo "$BEAD_JSON" | jq -r '.title // .description' | head -c 50)
    ITERATION=$((ITERATION + 1))

    log "[$ITERATION] Picked up bead $BEAD_ID: $BEAD_TITLE"

    # Build enriched prompt
    PROMPT_FILE="/tmp/ringmaster-prompt-$BEAD_ID.txt"
    ringmaster build-prompt "$BEAD_ID" -o "$PROMPT_FILE" 2>&1 | tee -a "$LOG_FILE"

    if [ ! -f "$PROMPT_FILE" ]; then
        log "ERROR: Failed to build prompt for $BEAD_ID"
        ringmaster report-result "$BEAD_ID" --status failed --reason "Failed to build prompt" 2>&1 | tee -a "$LOG_FILE"
        continue
    fi

    # Export environment variables
    export RINGMASTER_PROMPT_FILE="$PROMPT_FILE"
    export RINGMASTER_TASK_ID="$BEAD_ID"
    export RINGMASTER_WORKER_ID="$WORKER_ID"

    # Execute worker command based on type
    EXIT_CODE=0
    case "$WORKER_TYPE" in
        claude-code)
            log "Running Claude Code..."
            claude --print --dangerously-skip-permissions \\
                "$(cat $PROMPT_FILE)" \\
                2>&1 | tee -a "$LOG_FILE" || EXIT_CODE=$?
            ;;
        aider)
            log "Running Aider..."
            aider --yes \\
                --message "$(cat $PROMPT_FILE)" \\
                2>&1 | tee -a "$LOG_FILE" || EXIT_CODE=$?
            ;;
        *)
            log "ERROR: Unknown worker type: $WORKER_TYPE"
            EXIT_CODE=1
            ;;
    esac

    # Check for changes and commit if any
    CHANGES_COMMITTED=""
    if [ $EXIT_CODE -eq 0 ]; then
        if git diff --quiet && git diff --cached --quiet; then
            log "[$ITERATION] No changes detected"
        else
            log "[$ITERATION] Committing changes..."
            git add -A
            git commit -m "task($BEAD_ID): $BEAD_TITLE

Completed by worker: $WORKER_NAME ($WORKER_TYPE)
Task ID: $BEAD_ID" 2>&1 | tee -a "$LOG_FILE" || true
            CHANGES_COMMITTED="--changes-committed"
        fi
    fi

    # Report result
    if [ $EXIT_CODE -eq 0 ]; then
        log "[$ITERATION] Completed bead $BEAD_ID successfully"
        ringmaster report-result "$BEAD_ID" --status completed $CHANGES_COMMITTED 2>&1 | tee -a "$LOG_FILE"
    else
        log "[$ITERATION] Failed bead $BEAD_ID with exit code $EXIT_CODE"
        ringmaster report-result "$BEAD_ID" --status failed --exit-code $EXIT_CODE 2>&1 | tee -a "$LOG_FILE"
    fi

    # Cleanup prompt file
    rm -f "$PROMPT_FILE"

    log "[$ITERATION] Finished bead $BEAD_ID"
done
'''

    def __init__(
        self,
        log_dir: Path | None = None,
        worktree_dir: Path | None = None,
        db_path: Path | None = None,
        script_dir: Path | None = None,
    ):
        """Initialize the worker spawner.

        Args:
            log_dir: Directory for worker log files.
            worktree_dir: Base directory for worker worktrees.
            db_path: Path to ringmaster database.
            script_dir: Directory to store generated worker scripts.
        """
        # Use ~/.ringmaster/logs for user-writable default
        self.log_dir = log_dir or Path.home() / ".ringmaster" / "logs" / "workers"
        self.worktree_dir = worktree_dir
        self.db_path = db_path or Path(".ringmaster/ringmaster.db")
        self.script_dir = script_dir or Path("/tmp/ringmaster-workers")

        self._spawned_workers: dict[str, SpawnedWorker] = {}

    def _check_tmux_available(self) -> bool:
        """Check if tmux is available on the system."""
        return shutil.which("tmux") is not None

    def _get_tmux_session_name(self, worker_id: str) -> str:
        """Generate tmux session name for a worker."""
        return f"rm-worker-{worker_id}"

    def _generate_worker_script(
        self,
        worker_id: str,
        worker_name: str,
        worker_type: str,
        capabilities: list[str] | None = None,
        generated_script: str | None = None,
    ) -> Path:
        """Generate the worker bash script.

        Args:
            worker_id: Unique worker identifier.
            worker_name: Human-readable worker name.
            worker_type: Type of worker (claude-code, aider, codex, etc.).
            capabilities: List of worker capabilities.
            generated_script: LLM-generated complete bash script (takes priority).

        Returns:
            Path to the generated script.
        """
        # Ensure script directory exists
        self.script_dir.mkdir(parents=True, exist_ok=True)

        # Use generated script if available, otherwise fall back to template
        if generated_script:
            script_content = generated_script
        else:
            log_path = self.log_dir / f"{worker_id}.log"
            script_content = self.WORKER_SCRIPT_TEMPLATE.format(
                worker_id=worker_id,
                worker_name=worker_name,
                worker_type=worker_type,
                log_path=str(log_path),
                capabilities=",".join(capabilities or []),
            )

        # Write script
        script_path = self.script_dir / f"worker-{worker_id}.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)

        return script_path

    async def spawn(
        self,
        worker_id: str,
        worker_name: str,
        worker_type: str,
        capabilities: list[str] | None = None,
        generated_script: str | None = None,
    ) -> SpawnedWorker:
        """Spawn a worker in a tmux session.

        Args:
            worker_id: Unique worker identifier.
            worker_name: Human-readable worker name.
            worker_type: Type of worker (claude-code, aider, codex, etc.).
            capabilities: List of worker capabilities.
            generated_script: LLM-generated complete bash script (optional).

        Returns:
            SpawnedWorker instance.

        Raises:
            RuntimeError: If tmux is not available or spawning fails.
        """
        if not self._check_tmux_available():
            raise RuntimeError("tmux is not available on this system")

        # Check if worker already exists
        if worker_id in self._spawned_workers:
            existing = self._spawned_workers[worker_id]
            if await self.is_running(worker_id):
                logger.warning(f"Worker {worker_id} is already running")
                return existing

        # Generate worker script
        script_path = self._generate_worker_script(
            worker_id=worker_id,
            worker_name=worker_name,
            worker_type=worker_type,
            capabilities=capabilities,
            generated_script=generated_script,
        )

        # Create tmux session
        session_name = self._get_tmux_session_name(worker_id)
        log_path = self.log_dir / f"{worker_id}.log"

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Spawn in tmux
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "new-session",
            "-d",
            "-s",
            session_name,
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"Failed to spawn worker {worker_id}: {error_msg}")

        # Create worker record
        worker = SpawnedWorker(
            worker_id=worker_id,
            worker_type=worker_type,
            tmux_session=session_name,
            worktree_path=None,
            log_path=str(log_path),
            status=SpawnStatus.RUNNING,
        )

        self._spawned_workers[worker_id] = worker
        logger.info(f"Spawned worker {worker_id} in tmux session {session_name}")

        return worker

    async def is_running(self, worker_id: str) -> bool:
        """Check if a worker's tmux session is running.

        Args:
            worker_id: Worker identifier.

        Returns:
            True if the worker is running.
        """
        session_name = self._get_tmux_session_name(worker_id)

        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "has-session",
            "-t",
            session_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        return proc.returncode == 0

    async def kill(self, worker_id: str) -> bool:
        """Kill a worker's tmux session.

        Args:
            worker_id: Worker identifier.

        Returns:
            True if the worker was killed.
        """
        session_name = self._get_tmux_session_name(worker_id)

        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "kill-session",
            "-t",
            session_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if worker_id in self._spawned_workers:
            self._spawned_workers[worker_id].status = SpawnStatus.STOPPED
            del self._spawned_workers[worker_id]

        logger.info(f"Killed worker {worker_id}")
        return proc.returncode == 0

    async def list_sessions(self) -> list[str]:
        """List all ringmaster worker tmux sessions.

        Returns:
            List of session names.
        """
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "list-sessions",
            "-F",
            "#{session_name}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return []

        sessions = stdout.decode().strip().split("\n")
        return [s for s in sessions if s.startswith("rm-worker-")]

    async def get_worker_info(self, worker_id: str) -> SpawnedWorker | None:
        """Get information about a spawned worker.

        Args:
            worker_id: Worker identifier.

        Returns:
            SpawnedWorker instance or None if not found.
        """
        if worker_id in self._spawned_workers:
            worker = self._spawned_workers[worker_id]
            # Update status
            if await self.is_running(worker_id):
                worker.status = SpawnStatus.RUNNING
            else:
                worker.status = SpawnStatus.STOPPED
            return worker
        return None

    async def get_output(
        self, worker_id: str, lines: int = 100
    ) -> str | None:
        """Get recent output from a worker's log file.

        Args:
            worker_id: Worker identifier.
            lines: Number of lines to retrieve.

        Returns:
            Log output or None if not available.
        """
        log_path = self.log_dir / f"{worker_id}.log"

        if not log_path.exists():
            return None

        proc = await asyncio.create_subprocess_exec(
            "tail",
            "-n",
            str(lines),
            str(log_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        stdout, _ = await proc.communicate()

        if proc.returncode == 0:
            return stdout.decode()
        return None

    def attach_command(self, worker_id: str) -> str:
        """Get the command to attach to a worker's tmux session.

        Args:
            worker_id: Worker identifier.

        Returns:
            Command string to attach to the session.
        """
        session_name = self._get_tmux_session_name(worker_id)
        return f"tmux attach-session -t {session_name}"

    async def send_signal(self, worker_id: str, signal: str = "SIGINT") -> bool:
        """Send a signal to a worker.

        Args:
            worker_id: Worker identifier.
            signal: Signal name (e.g., SIGINT, SIGTERM).

        Returns:
            True if signal was sent.
        """
        session_name = self._get_tmux_session_name(worker_id)

        # Get the pane PID
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "list-panes",
            "-t",
            session_name,
            "-F",
            "#{pane_pid}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        stdout, _ = await proc.communicate()

        if proc.returncode != 0 or not stdout:
            return False

        pane_pid = stdout.decode().strip().split("\n")[0]

        # Send signal to the process
        kill_proc = await asyncio.create_subprocess_exec(
            "kill",
            f"-{signal}",
            pane_pid,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await kill_proc.wait()

        return kill_proc.returncode == 0

    async def cleanup_stale(self) -> list[str]:
        """Clean up stale worker sessions and scripts.

        Returns:
            List of cleaned up worker IDs.
        """
        cleaned = []

        # Find sessions that are no longer running
        for worker_id in list(self._spawned_workers.keys()):
            if not await self.is_running(worker_id):
                del self._spawned_workers[worker_id]
                cleaned.append(worker_id)

        # Clean up old script files
        if self.script_dir.exists():
            for script in self.script_dir.glob("worker-*.sh"):
                # Extract worker ID from script name
                wid = script.stem.replace("worker-", "")
                if not await self.is_running(wid):
                    script.unlink()

        return cleaned
