"""Tests for simplified natural language worker configuration."""

import pytest

from ringmaster.worker.natural import (
    WorkerDefinition,
    WorkerRegistry,
    create_worker,
    get_worker,
    list_all_workers,
    list_workers,
    parse_worker_description,
    register_worker,
)


class TestWorkerDefinition:
    """Test the simplified WorkerDefinition class."""

    def test_worker_definition_fields(self):
        """Worker has just name, description, model, start_script."""
        worker = WorkerDefinition(
            name="test-worker",
            description="Test worker",
            model="test-model",
            start_script="test --model {model} {prompt}",
        )
        assert worker.name == "test-worker"
        assert worker.description == "Test worker"
        assert worker.model == "test-model"
        assert worker.start_script == "test --model {model} {prompt}"

    def test_build_command_with_model_and_prompt(self):
        """Build command substitutes both model and prompt placeholders."""
        worker = WorkerDefinition(
            name="test",
            start_script="test --model {model} -- {prompt}",
            model="default-model",
        )
        cmd = worker.build_command(model="my-model", prompt="hello world")
        assert "my-model" in " ".join(cmd)
        assert "hello" in cmd
        assert "world" in cmd

    def test_build_command_with_default_model(self):
        """Build command uses default model if no override."""
        worker = WorkerDefinition(
            name="test",
            start_script="test --model {model} {prompt}",
            model="default-model",
        )
        cmd = worker.build_command(prompt="test")
        assert "default-model" in " ".join(cmd)

    def test_build_command_without_prompt(self):
        """Build command works even without prompt."""
        worker = WorkerDefinition(
            name="test",
            start_script="test --model {model}",
            model="test-model",
        )
        cmd = worker.build_command()
        assert len(cmd) > 0
        assert "test" in cmd[0]


class TestWorkerRegistry:
    """Test the worker registry."""

    def test_list_all_workers(self):
        """Can list all registered workers."""
        workers = list_all_workers()
        assert isinstance(workers, list)
        assert len(workers) >= 7  # claude-code, aider, cursor, opencode, codex, goose, kilo

    def test_list_available_workers(self):
        """Can list only available workers."""
        workers = list_workers()
        assert isinstance(workers, list)
        # At least claude-code should be available in test environment
        available_names = [w.name for w in workers]
        # Some workers may not be installed, so we just check the list is valid
        for worker in workers:
            assert worker.name
            assert worker.start_script

    def test_get_worker(self):
        """Can get specific worker by name."""
        worker = get_worker("claude-code")
        assert worker is not None
        assert worker.name == "claude-code"
        assert worker.model == "claude-sonnet-4-20250514"
        assert "claude" in worker.start_script

    def test_get_unknown_worker(self):
        """Unknown worker returns None."""
        worker = get_worker("unknown-worker")
        assert worker is None

    def test_register_custom_worker(self):
        """Can register a custom worker."""
        custom = WorkerDefinition(
            name="custom-worker",
            description="My custom worker",
            model="custom-model",
            start_script="custom --model {model} {prompt}",
        )
        register_worker(custom)

        retrieved = get_worker("custom-worker")
        assert retrieved is not None
        assert retrieved.name == "custom-worker"
        assert retrieved.model == "custom-model"


class TestNaturalLanguageParser:
    """Test natural language parsing."""

    def test_parse_claude_code_with_sonnet(self):
        """Parse claude code with sonnet model."""
        result = parse_worker_description("claude code with sonnet")
        assert result.success
        assert result.name == "claude-code"
        assert result.model == "claude-sonnet-4-20250514"
        assert result.start_script is not None

    def test_parse_claude_code_with_opus(self):
        """Parse claude code with opus model."""
        result = parse_worker_description("claude code using opus")
        assert result.success
        assert result.name == "claude-code"
        assert result.model == "claude-opus-4-20250514"

    def test_parse_aider(self):
        """Parse aider worker."""
        result = parse_worker_description("aider")
        assert result.success
        assert result.name == "aider"
        assert result.model == "claude-3-5-sonnet-20241022"

    def test_parse_cursor(self):
        """Parse cursor worker."""
        result = parse_worker_description("cursor")
        assert result.success
        assert result.name == "cursor"
        assert result.model == "gpt-4o"

    def test_parse_unknown_worker(self):
        """Unknown worker returns error."""
        result = parse_worker_description("unknown-tool")
        assert not result.success
        assert result.error is not None
        assert "Could not identify worker" in result.error

    def test_parse_returns_start_script(self):
        """Parse result includes start script."""
        result = parse_worker_description("claude code")
        assert result.start_script is not None
        assert "claude" in result.start_script
        assert "{model}" in result.start_script
        assert "{prompt}" in result.start_script


class TestCreateWorker:
    """Test worker creation from natural language."""

    def test_create_claude_code_with_sonnet(self):
        """Create claude code worker with specific model."""
        worker = create_worker("claude code with sonnet")
        assert worker.name == "claude-code"
        assert worker.model == "claude-sonnet-4-20250514"
        assert worker.start_script is not None

    def test_create_claude_code_with_opus(self):
        """Create claude code worker with opus model."""
        worker = create_worker("claude code using opus")
        assert worker.name == "claude-code"
        assert worker.model == "claude-opus-4-20250514"

    def test_create_aider(self):
        """Create aider worker."""
        worker = create_worker("aider")
        assert worker.name == "aider"
        assert worker.model == "claude-3-5-sonnet-20241022"

    def test_create_invalid_description_raises(self):
        """Invalid description raises ValueError."""
        with pytest.raises(ValueError, match="Could not parse"):
            create_worker("not a valid worker")

    def test_created_worker_can_build_command(self):
        """Created worker can build commands."""
        worker = create_worker("claude code with sonnet")
        cmd = worker.build_command(prompt="test prompt")
        assert isinstance(cmd, list)
        assert len(cmd) > 0


class TestDefaultWorkers:
    """Test default worker definitions."""

    def test_claude_code_default(self):
        """Claude Code worker has correct defaults."""
        worker = get_worker("claude-code")
        assert worker.name == "claude-code"
        assert worker.model == "claude-sonnet-4-20250514"
        assert "claude" in worker.start_script.lower()
        assert "{model}" in worker.start_script
        assert "{prompt}" in worker.start_script

    def test_aider_default(self):
        """Aider worker has correct defaults."""
        worker = get_worker("aider")
        assert worker.name == "aider"
        assert worker.model == "claude-3-5-sonnet-20241022"
        assert "aider" in worker.start_script.lower()

    def test_all_default_workers_have_required_fields(self):
        """All default workers have required fields."""
        workers = list_all_workers()
        for worker in workers:
            assert worker.name
            assert worker.start_script
            assert "{prompt}" in worker.start_script
            # All workers should have a model defined
            assert worker.model is not None


class TestIntegration:
    """Integration tests for the simplified workflow."""

    def test_full_workflow_parse_create_execute(self):
        """Test full workflow: parse -> create -> build command."""
        # Parse natural language
        result = parse_worker_description("claude code with opus")
        assert result.success

        # Create worker
        worker = create_worker("claude code with opus")
        assert worker.model == "claude-opus-4-20250514"

        # Build command
        cmd = worker.build_command(prompt="fix the bug")
        assert "claude" in cmd[0].lower()
        assert "claude-opus-4-20250514" in " ".join(cmd)

    def test_register_and_use_custom_worker(self):
        """Test registering a custom worker and using it."""
        # Register custom worker
        custom = WorkerDefinition(
            name="my-custom",
            description="My custom tool",
            model="custom-model-1",
            start_script="my-tool --model {model} --prompt {prompt}",
        )
        register_worker(custom)

        # Can retrieve it
        worker = get_worker("my-custom")
        assert worker is not None
        assert worker.model == "custom-model-1"

        # Can build command
        cmd = worker.build_command(prompt="test")
        assert "my-tool" in cmd
        assert "custom-model-1" in " ".join(cmd)


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_description(self):
        """Empty description returns error."""
        result = parse_worker_description("")
        assert not result.success

    def test_case_insensitive(self):
        """Parsing is case-insensitive."""
        result1 = parse_worker_description("CLAUDE CODE WITH SONNET")
        result2 = parse_worker_description("claude code with sonnet")
        assert result1.name == result2.name
        assert result1.model == result2.model

    def test_extra_words_dont_break_parsing(self):
        """Extra words in description don't break parsing."""
        result = parse_worker_description(
            "I would like to use claude code with the sonnet model please"
        )
        assert result.success
        assert result.name == "claude-code"

    def test_model_variations(self):
        """Different model variations work."""
        test_cases = [
            ("claude code with sonnet-4", "claude-sonnet-4-20250514"),
            ("claude code with opus", "claude-opus-4-20250514"),
            ("claude code with haiku", "claude-3-5-haiku-20241022"),
        ]
        for desc, expected_model in test_cases:
            result = parse_worker_description(desc)
            assert result.model == expected_model, f"Failed for: {desc}"

    def test_worker_without_model_override(self):
        """Can build command without overriding model."""
        worker = get_worker("claude-code")
        cmd = worker.build_command(prompt="test")
        # Should use default model
        assert worker.model in " ".join(cmd) or "claude" in " ".join(cmd).lower()
