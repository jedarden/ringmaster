"""Tests for worker spawner."""

import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ringmaster.worker.spawner import SpawnedWorker, SpawnStatus, WorkerSpawner


class TestWorkerSpawner:
    """Tests for WorkerSpawner class."""

    @pytest.fixture
    def spawner(self, tmp_path: Path) -> WorkerSpawner:
        """Create a spawner with temporary directories."""
        return WorkerSpawner(
            log_dir=tmp_path / "logs",
            db_path=tmp_path / "test.db",
            script_dir=tmp_path / "scripts",
        )

    def test_generate_worker_script_claude_code(self, spawner: WorkerSpawner) -> None:
        """Test generating a Claude Code worker script."""
        script_path = spawner._generate_worker_script(
            worker_id="test-worker-1",
            worker_type="claude-code",
            capabilities=["python", "typescript"],
            worktree_path="/workspace/project",
        )

        assert script_path.exists()
        content = script_path.read_text()

        # Check script contains expected elements
        assert 'WORKER_ID="test-worker-1"' in content
        assert 'WORKER_TYPE="claude-code"' in content
        assert 'CAPABILITIES="python,typescript"' in content
        assert 'WORKTREE_PATH="/workspace/project"' in content
        assert "claude --print --dangerously-skip-permissions" in content
        assert "ringmaster pull-bead" in content
        assert "ringmaster build-prompt" in content
        assert "ringmaster report-result" in content

    def test_generate_worker_script_aider(self, spawner: WorkerSpawner) -> None:
        """Test generating an Aider worker script."""
        script_path = spawner._generate_worker_script(
            worker_id="aider-1",
            worker_type="aider",
            capabilities=["python"],
        )

        assert script_path.exists()
        content = script_path.read_text()

        assert 'WORKER_TYPE="aider"' in content
        assert "aider --yes --no-git" in content
        assert "--message" in content

    def test_generate_worker_script_codex(self, spawner: WorkerSpawner) -> None:
        """Test generating a Codex worker script."""
        script_path = spawner._generate_worker_script(
            worker_id="codex-1",
            worker_type="codex",
        )

        assert script_path.exists()
        content = script_path.read_text()

        assert 'WORKER_TYPE="codex"' in content
        assert "codex --quiet --auto-approve" in content

    def test_generate_worker_script_goose(self, spawner: WorkerSpawner) -> None:
        """Test generating a Goose worker script."""
        script_path = spawner._generate_worker_script(
            worker_id="goose-1",
            worker_type="goose",
        )

        assert script_path.exists()
        content = script_path.read_text()

        assert 'WORKER_TYPE="goose"' in content
        assert "goose run --non-interactive" in content

    def test_generate_worker_script_generic_with_custom_command(
        self, spawner: WorkerSpawner
    ) -> None:
        """Test generating a generic worker script with custom command."""
        script_path = spawner._generate_worker_script(
            worker_id="custom-1",
            worker_type="generic",
            custom_command="my-custom-tool --auto",
        )

        assert script_path.exists()
        content = script_path.read_text()

        assert 'WORKER_TYPE="generic"' in content
        # Generic workers use WORKER_COMMAND env var
        assert "WORKER_COMMAND" in content
        assert "eval" in content  # Command is eval'd from WORKER_COMMAND

    def test_tmux_session_name(self, spawner: WorkerSpawner) -> None:
        """Test tmux session name generation."""
        assert spawner._get_tmux_session_name("worker-1") == "rm-worker-worker-1"
        assert spawner._get_tmux_session_name("claude") == "rm-worker-claude"

    def test_attach_command(self, spawner: WorkerSpawner) -> None:
        """Test attach command generation."""
        cmd = spawner.attach_command("worker-1")
        assert cmd == "tmux attach-session -t rm-worker-worker-1"

    @pytest.mark.asyncio
    async def test_check_tmux_available_mock(self, spawner: WorkerSpawner) -> None:
        """Test tmux availability check."""
        # Mock shutil.which
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/tmux"
            assert spawner._check_tmux_available() is True

            mock_which.return_value = None
            assert spawner._check_tmux_available() is False

    @pytest.mark.asyncio
    async def test_spawn_no_tmux(self, spawner: WorkerSpawner) -> None:
        """Test spawn fails gracefully when tmux is not available."""
        with patch.object(spawner, "_check_tmux_available", return_value=False):
            with pytest.raises(RuntimeError, match="tmux is not available"):
                await spawner.spawn("worker-1", "claude-code")

    @pytest.mark.asyncio
    async def test_spawn_creates_worker_record(self, spawner: WorkerSpawner) -> None:
        """Test that spawn creates a SpawnedWorker record."""
        # Mock the subprocess calls
        with patch.object(spawner, "_check_tmux_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                # Create a mock process
                mock_process = AsyncMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_process

                worker = await spawner.spawn(
                    worker_id="test-1",
                    worker_type="claude-code",
                    capabilities=["python"],
                )

                assert isinstance(worker, SpawnedWorker)
                assert worker.worker_id == "test-1"
                assert worker.worker_type == "claude-code"
                assert worker.status == SpawnStatus.RUNNING
                assert "rm-worker-test-1" in worker.tmux_session

    @pytest.mark.asyncio
    async def test_spawn_idempotent(self, spawner: WorkerSpawner) -> None:
        """Test that spawning an already-running worker returns existing record."""
        with patch.object(spawner, "_check_tmux_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = AsyncMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_process

                # First spawn
                worker1 = await spawner.spawn("worker-1", "claude-code")

                # Mock is_running to return True
                with patch.object(spawner, "is_running", return_value=True):
                    # Second spawn should return same worker
                    worker2 = await spawner.spawn("worker-1", "claude-code")
                    assert worker2.worker_id == worker1.worker_id

    @pytest.mark.asyncio
    async def test_is_running_mock(self, spawner: WorkerSpawner) -> None:
        """Test is_running check."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_exec.return_value = mock_process

            # Running
            mock_process.returncode = 0
            result = await spawner.is_running("worker-1")
            assert result is True

            # Not running
            mock_process.returncode = 1
            result = await spawner.is_running("worker-1")
            assert result is False

    @pytest.mark.asyncio
    async def test_kill_mock(self, spawner: WorkerSpawner) -> None:
        """Test killing a worker."""
        with patch.object(spawner, "_check_tmux_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = AsyncMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.wait = AsyncMock()
                mock_exec.return_value = mock_process

                # First spawn
                await spawner.spawn("worker-1", "claude-code")
                assert "worker-1" in spawner._spawned_workers

                # Kill
                result = await spawner.kill("worker-1")
                assert result is True
                assert "worker-1" not in spawner._spawned_workers

    @pytest.mark.asyncio
    async def test_list_sessions_mock(self, spawner: WorkerSpawner) -> None:
        """Test listing sessions."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(
                return_value=(
                    b"rm-worker-claude-1\nrm-worker-aider-1\nother-session\n",
                    b"",
                )
            )
            mock_exec.return_value = mock_process

            sessions = await spawner.list_sessions()
            assert "rm-worker-claude-1" in sessions
            assert "rm-worker-aider-1" in sessions
            assert "other-session" not in sessions  # Not a ringmaster session

    @pytest.mark.asyncio
    async def test_get_output(self, spawner: WorkerSpawner) -> None:
        """Test getting worker output from log file."""
        # Create a test log file
        spawner.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = spawner.log_dir / "worker-1.log"
        log_file.write_text("line 1\nline 2\nline 3\n")

        output = await spawner.get_output("worker-1", lines=2)
        assert output is not None
        assert "line 2" in output
        assert "line 3" in output

    @pytest.mark.asyncio
    async def test_get_output_no_file(self, spawner: WorkerSpawner) -> None:
        """Test getting output when log file doesn't exist."""
        output = await spawner.get_output("nonexistent", lines=10)
        assert output is None

    @pytest.mark.asyncio
    async def test_get_worker_info(self, spawner: WorkerSpawner) -> None:
        """Test getting worker info."""
        with patch.object(spawner, "_check_tmux_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = AsyncMock()
                mock_process.returncode = 0
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.wait = AsyncMock()
                mock_exec.return_value = mock_process

                # Spawn a worker
                await spawner.spawn("worker-1", "claude-code")

                # Get info
                info = await spawner.get_worker_info("worker-1")
                assert info is not None
                assert info.worker_id == "worker-1"
                assert info.status == SpawnStatus.RUNNING

                # Non-existent worker
                info = await spawner.get_worker_info("nonexistent")
                assert info is None

    @pytest.mark.asyncio
    async def test_send_signal_mock(self, spawner: WorkerSpawner) -> None:
        """Test sending signal to worker."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # First call to get pane PID
            pane_proc = AsyncMock()
            pane_proc.returncode = 0
            pane_proc.communicate = AsyncMock(return_value=(b"12345\n", b""))

            # Second call to kill
            kill_proc = AsyncMock()
            kill_proc.returncode = 0
            kill_proc.wait = AsyncMock()

            mock_exec.side_effect = [pane_proc, kill_proc]

            result = await spawner.send_signal("worker-1", "SIGINT")
            assert result is True

    @pytest.mark.asyncio
    async def test_cleanup_stale(self, spawner: WorkerSpawner) -> None:
        """Test cleaning up stale workers."""
        # Create some script files
        spawner.script_dir.mkdir(parents=True, exist_ok=True)
        (spawner.script_dir / "worker-stale.sh").write_text("#!/bin/bash\necho test")

        with patch.object(spawner, "is_running", return_value=False):
            cleaned = await spawner.cleanup_stale()
            # Script should be cleaned up
            assert not (spawner.script_dir / "worker-stale.sh").exists()


class TestSpawnedWorker:
    """Tests for SpawnedWorker dataclass."""

    def test_spawned_worker_defaults(self) -> None:
        """Test SpawnedWorker default values."""
        worker = SpawnedWorker(
            worker_id="test-1",
            worker_type="claude-code",
            tmux_session="rm-worker-test-1",
            worktree_path=None,
            log_path=None,
        )

        assert worker.status == SpawnStatus.STARTING
        assert worker.started_at is not None
        assert worker.pid is None

    def test_spawn_status_enum(self) -> None:
        """Test SpawnStatus enum values."""
        assert SpawnStatus.STARTING == "starting"
        assert SpawnStatus.RUNNING == "running"
        assert SpawnStatus.STOPPED == "stopped"
        assert SpawnStatus.FAILED == "failed"
