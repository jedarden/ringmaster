"""Tests for model routing based on task complexity."""

from uuid import uuid4

import pytest

from ringmaster.domain.enums import Priority
from ringmaster.domain.models import Epic, Subtask, Task
from ringmaster.queue.routing import (
    COMPLEX_KEYWORDS,
    MODEL_SUGGESTIONS,
    SIMPLE_KEYWORDS,
    ComplexitySignals,
    ModelTier,
    TaskComplexity,
    complexity_from_score,
    estimate_complexity,
    get_model_for_worker_type,
    select_model_for_task,
    tier_from_complexity,
)


@pytest.fixture
def project_id():
    return uuid4()


class TestEstimateComplexity:
    """Tests for complexity estimation."""

    def test_simple_task_with_simple_keywords(self, project_id):
        """Simple keywords should reduce complexity score."""
        task = Task(
            project_id=project_id,
            title="Fix typo in README",
            description="There's a typo on line 42. Change 'teh' to 'the'.",
        )
        signals = estimate_complexity(task)

        assert signals.simple_keyword_matches >= 1
        assert signals.raw_score <= 0  # Simple

    def test_complex_task_with_complex_keywords(self, project_id):
        """Complex keywords should increase complexity score."""
        task = Task(
            project_id=project_id,
            title="Migrate authentication system",
            description="Refactor the auth module to use JWT. This is a security-critical change "
            "that requires updating the database schema and API design.",
        )
        signals = estimate_complexity(task)

        assert signals.complex_keyword_matches >= 3  # migrate, auth, security, schema, api design
        assert signals.raw_score > 2  # Complex

    def test_file_count_detection_from_description(self, project_id):
        """Should detect file patterns in description."""
        task = Task(
            project_id=project_id,
            title="Update configuration files",
            description="Modify config.py, settings.json, and docker.yaml to add new environment variables.",
        )
        signals = estimate_complexity(task)

        assert signals.file_count >= 2  # .py, .json, .yaml

    def test_epic_increases_complexity(self, project_id):
        """Epics should be marked as complex."""
        epic = Epic(
            project_id=project_id,
            title="Build user authentication system",
            description="Complete auth system",
        )
        signals = estimate_complexity(epic)

        assert signals.is_epic
        assert signals.raw_score >= 2  # Epic bonus

    def test_subtask_decreases_complexity(self, project_id):
        """Subtasks should reduce complexity."""
        subtask = Subtask(
            project_id=project_id,
            parent_id="bd-12345678",
            title="Add validation to email field",
            description="Simple field validation",
        )
        signals = estimate_complexity(subtask)

        assert signals.is_subtask
        assert signals.raw_score <= 0  # Subtask reduction

    def test_critical_priority_increases_complexity(self, project_id):
        """P0 priority should increase complexity."""
        task = Task(
            project_id=project_id,
            title="Fix production bug",
            description="Urgent fix needed",
            priority=Priority.P0,
        )
        signals = estimate_complexity(task)

        assert signals.is_critical
        # P0 adds +1 to score

    def test_long_description_increases_complexity(self, project_id):
        """Long descriptions often indicate complex tasks."""
        long_desc = "Detailed specification " * 200  # > 2000 chars
        task = Task(
            project_id=project_id,
            title="Complex feature",
            description=long_desc,
        )
        signals = estimate_complexity(task)

        assert signals.description_length > 2000


class TestComplexityFromScore:
    """Tests for score to complexity mapping."""

    def test_negative_score_is_simple(self):
        assert complexity_from_score(-2) == TaskComplexity.SIMPLE

    def test_zero_score_is_simple(self):
        assert complexity_from_score(0) == TaskComplexity.SIMPLE

    def test_score_one_is_moderate(self):
        assert complexity_from_score(1) == TaskComplexity.MODERATE

    def test_score_two_is_moderate(self):
        assert complexity_from_score(2) == TaskComplexity.MODERATE

    def test_score_three_is_complex(self):
        assert complexity_from_score(3) == TaskComplexity.COMPLEX

    def test_high_score_is_complex(self):
        assert complexity_from_score(10) == TaskComplexity.COMPLEX


class TestTierFromComplexity:
    """Tests for complexity to tier mapping."""

    def test_simple_maps_to_fast(self):
        assert tier_from_complexity(TaskComplexity.SIMPLE) == ModelTier.FAST

    def test_moderate_maps_to_balanced(self):
        assert tier_from_complexity(TaskComplexity.MODERATE) == ModelTier.BALANCED

    def test_complex_maps_to_powerful(self):
        assert tier_from_complexity(TaskComplexity.COMPLEX) == ModelTier.POWERFUL

    def test_research_downgrade(self):
        """Research tasks should use balanced even for complex estimation."""
        tier = tier_from_complexity(TaskComplexity.COMPLEX, task_type="research")
        assert tier == ModelTier.BALANCED

    def test_validation_uses_balanced(self):
        """Validation tasks should use balanced tier."""
        tier = tier_from_complexity(TaskComplexity.COMPLEX, task_type="validation")
        assert tier == ModelTier.BALANCED


class TestSelectModelForTask:
    """Tests for full routing decision."""

    def test_simple_task_routes_to_fast(self, project_id):
        task = Task(
            project_id=project_id,
            title="Fix typo",
            description="Fix a typo in the README file",
        )
        result = select_model_for_task(task)

        assert result.complexity == TaskComplexity.SIMPLE
        assert result.tier == ModelTier.FAST
        assert len(result.suggested_models) > 0
        assert "haiku" in result.suggested_models[0].lower() or "mini" in result.suggested_models[0].lower()

    def test_complex_task_routes_to_powerful(self, project_id):
        task = Task(
            project_id=project_id,
            title="Architect new microservices",
            description="Design and implement a distributed authentication system "
            "with security hardening and database schema migration.",
            priority=Priority.P0,
        )
        result = select_model_for_task(task)

        assert result.complexity == TaskComplexity.COMPLEX
        assert result.tier == ModelTier.POWERFUL
        assert len(result.suggested_models) > 0
        assert "opus" in result.suggested_models[0].lower() or "o1" in result.suggested_models[0].lower()

    def test_result_includes_reasoning(self, project_id):
        task = Task(
            project_id=project_id,
            title="Refactor auth module",
            description="Major refactoring needed",
        )
        result = select_model_for_task(task)

        assert result.reasoning
        assert "Score" in result.reasoning

    def test_result_includes_signals(self, project_id):
        task = Task(
            project_id=project_id,
            title="Test task",
            description="Test description",
        )
        result = select_model_for_task(task)

        assert isinstance(result.signals, ComplexitySignals)
        assert hasattr(result.signals, "raw_score")


class TestGetModelForWorkerType:
    """Tests for worker-specific model selection."""

    def test_claude_code_fast_tier(self):
        model = get_model_for_worker_type(ModelTier.FAST, "claude-code")
        assert model is not None
        assert "haiku" in model.lower()

    def test_claude_code_balanced_tier(self):
        model = get_model_for_worker_type(ModelTier.BALANCED, "claude-code")
        assert model is not None
        assert "sonnet" in model.lower()

    def test_claude_code_powerful_tier(self):
        model = get_model_for_worker_type(ModelTier.POWERFUL, "claude-code")
        assert model is not None
        assert "opus" in model.lower()

    def test_codex_uses_openai_models(self):
        model = get_model_for_worker_type(ModelTier.BALANCED, "codex")
        assert model is not None
        assert "gpt" in model.lower()

    def test_unknown_worker_returns_none(self):
        model = get_model_for_worker_type(ModelTier.BALANCED, "unknown-worker")
        assert model is None


class TestKeywordCoverage:
    """Tests for keyword detection coverage."""

    def test_simple_keywords_are_defined(self):
        assert len(SIMPLE_KEYWORDS) > 5
        assert "typo" in SIMPLE_KEYWORDS
        assert "rename" in SIMPLE_KEYWORDS

    def test_complex_keywords_are_defined(self):
        assert len(COMPLEX_KEYWORDS) > 10
        assert "architect" in COMPLEX_KEYWORDS
        assert "security" in COMPLEX_KEYWORDS

    def test_model_suggestions_for_all_tiers(self):
        for tier in ModelTier:
            assert tier in MODEL_SUGGESTIONS
            assert len(MODEL_SUGGESTIONS[tier]) > 0


class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_bug_fix_scenario(self, project_id):
        """Bug fixes should route to moderate unless marked simple."""
        task = Task(
            project_id=project_id,
            title="Fix null pointer exception in UserService",
            description="Users are experiencing crashes when logging in with empty email. "
            "Need to add null check in UserService.java.",
        )
        result = select_model_for_task(task)

        # Single file, straightforward fix -> simple or moderate
        assert result.complexity in [TaskComplexity.SIMPLE, TaskComplexity.MODERATE]

    def test_new_feature_scenario(self, project_id):
        """New features should consider scope."""
        task = Task(
            project_id=project_id,
            title="Add user profile settings page",
            description="Create a new settings page where users can update their profile, "
            "change password, and manage notifications. Update routes.tsx, "
            "ProfileSettings.tsx, and api/user.py.",
        )
        result = select_model_for_task(task)

        # Multiple files, moderate complexity
        assert result.complexity in [TaskComplexity.MODERATE, TaskComplexity.COMPLEX]

    def test_documentation_update_scenario(self, project_id):
        """Documentation updates should be simple."""
        task = Task(
            project_id=project_id,
            title="Update API documentation",
            description="Add comments to the authentication endpoints. Fix typos in README.md.",
        )
        result = select_model_for_task(task)

        # Simple keywords (comments, typos) -> simple
        assert result.complexity == TaskComplexity.SIMPLE
        assert result.tier == ModelTier.FAST
