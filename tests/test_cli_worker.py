"""Tests for worker CLI commands (pull-bead, build-prompt, report-result).

These tests verify the CLI commands work correctly for external worker scripts.
"""

import subprocess


class TestPullBeadCommand:
    """Tests for pull-bead command."""

    async def test_pull_bead_help(self):
        """Test pull-bead help text."""
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "pull-bead", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode == 0
        assert "Pull the next available task" in result.stdout
        assert "--capabilities" in result.stdout
        assert "--json" in result.stdout


class TestBuildPromptCommand:
    """Tests for build-prompt command."""

    async def test_build_prompt_help(self):
        """Test build-prompt help text."""
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "build-prompt", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode == 0
        assert "Build an enriched prompt" in result.stdout
        assert "--output" in result.stdout
        assert "--project-dir" in result.stdout


class TestReportResultCommand:
    """Tests for report-result command."""

    async def test_report_result_help(self):
        """Test report-result help text."""
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "report-result", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode == 0
        assert "Report task completion result" in result.stdout
        assert "--status" in result.stdout
        assert "completed" in result.stdout
        assert "failed" in result.stdout
        assert "--exit-code" in result.stdout
        assert "--reason" in result.stdout


class TestWorkerCLIIntegration:
    """Integration tests for the full worker CLI workflow."""

    async def test_cli_commands_registered(self):
        """Test that all worker commands are registered."""
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode == 0
        assert "pull-bead" in result.stdout
        assert "build-prompt" in result.stdout
        assert "report-result" in result.stdout

    async def test_pull_bead_requires_worker_id(self):
        """Test that pull-bead requires a worker ID argument."""
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "pull-bead"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode != 0
        assert "WORKER_ID" in result.stderr or "Missing argument" in result.stderr

    async def test_build_prompt_requires_task_id(self):
        """Test that build-prompt requires a task ID argument."""
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "build-prompt"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode != 0
        assert "TASK_ID" in result.stderr or "Missing argument" in result.stderr

    async def test_report_result_requires_task_id_and_status(self):
        """Test that report-result requires task ID and status."""
        # Missing task ID
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "report-result"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode != 0
        assert "TASK_ID" in result.stderr or "Missing argument" in result.stderr

        # Missing status
        result = subprocess.run(
            ["python", "-m", "ringmaster.cli", "report-result", "some-task-id"],
            capture_output=True,
            text=True,
            cwd="/home/coder/ringmaster",
            timeout=10,
        )

        assert result.returncode != 0
        assert "--status" in result.stderr or "Missing option" in result.stderr
