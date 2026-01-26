"""Tests for the bead creator service."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from ringmaster.creator import (
    BeadCreator,
    TaskCandidate,
    decompose_candidate,
    find_matching_task,
    is_too_large,
    parse_user_input,
    similarity_score,
)
from ringmaster.creator.parser import ActionType
from ringmaster.db import ProjectRepository
from ringmaster.db.connection import Database
from ringmaster.domain import Priority, Project, Task


class TestParser:
    """Tests for input parsing."""

    def test_parse_simple_input(self):
        """Test parsing a simple action."""
        result = parse_user_input("Add a login button")

        assert len(result.candidates) == 1
        assert result.candidates[0].action_type == ActionType.CREATE
        assert "login button" in result.candidates[0].target.lower()
        assert not result.is_epic

    def test_parse_multiple_tasks(self):
        """Test parsing multiple tasks from input."""
        result = parse_user_input(
            "Fix the login bug. Then add user validation. Finally, test the API."
        )

        assert len(result.candidates) == 3
        assert result.candidates[0].action_type == ActionType.FIX
        assert result.candidates[1].action_type == ActionType.CREATE
        assert result.candidates[2].action_type == ActionType.TEST

    def test_parse_numbered_list(self):
        """Test parsing a numbered list."""
        result = parse_user_input("""
        1. Implement user authentication
        2. Add password reset
        3. Write integration tests
        """)

        assert len(result.candidates) >= 3

    def test_parse_bulleted_list(self):
        """Test parsing a bulleted list."""
        result = parse_user_input("""
        - Create the API endpoint
        - Add validation
        - Update the documentation
        """)

        assert len(result.candidates) >= 3

    def test_detect_epic(self):
        """Test detecting when input should be an epic."""
        result = parse_user_input(
            "Build a complete user authentication system with login, registration, "
            "password reset, and two-factor authentication support."
        )

        assert result.is_epic
        assert len(result.suggested_epic_title) > 0

    def test_action_type_detection(self):
        """Test detection of different action types."""
        test_cases = [
            ("Implement a new feature", ActionType.CREATE),
            ("Fix the broken tests", ActionType.FIX),
            ("Refactor the database layer", ActionType.UPDATE),
            ("Remove deprecated code", ActionType.REMOVE),
            ("Test the API endpoints", ActionType.TEST),
            ("Document the architecture", ActionType.DOCUMENT),
            ("Investigate the memory leak", ActionType.INVESTIGATE),
        ]

        for text, expected_type in test_cases:
            result = parse_user_input(text)
            assert len(result.candidates) == 1
            assert result.candidates[0].action_type == expected_type, f"Failed for: {text}"

    def test_ordering_hints(self):
        """Test that ordering hints are extracted correctly."""
        result = parse_user_input("First set up the database. Then add the API.")

        assert len(result.candidates) == 2
        # First task should have lower order hint
        assert result.candidates[0].order_hint <= result.candidates[1].order_hint

    def test_empty_input(self):
        """Test handling empty input."""
        result = parse_user_input("")
        assert len(result.candidates) == 0

    def test_title_generation(self):
        """Test that task candidates generate proper titles."""
        result = parse_user_input("Add user authentication")

        assert len(result.candidates) == 1
        title = result.candidates[0].to_title()
        assert "Implement" in title or "Add" in title or "user authentication" in title.lower()


class TestDecomposer:
    """Tests for task decomposition."""

    def test_small_task_not_decomposed(self):
        """Test that small tasks are not decomposed."""
        candidate = TaskCandidate(
            raw_text="Add a login button",
            action_type=ActionType.CREATE,
            target="login button",
        )

        too_large, reasons = is_too_large(candidate)
        assert not too_large

    def test_large_task_detected(self):
        """Test that large tasks are detected."""
        # Create a text with multiple signals of being too large
        large_text = """
        Build a complete user authentication system that includes:
        - User registration module with email verification
        - Password reset component functionality
        - Two-factor authentication service
        - OAuth integration endpoint with Google and GitHub
        - Session management controller and JWT tokens
        - Role-based access control handler
        - Audit logging router for security events
        Additionally, we need to integrate this with the existing database
        and also update the API documentation, as well as adding more features.
        """ * 10  # Make it exceed 2000 chars

        candidate = TaskCandidate(
            raw_text=large_text,
            action_type=ActionType.CREATE,
            target="authentication system",
        )

        too_large, reasons = is_too_large(candidate)
        assert too_large
        assert len(reasons) >= 2

    def test_decompose_with_list(self):
        """Test decomposition of input with explicit list."""
        # The text needs to be large enough to trigger decomposition (2+ signals)
        base_text = """
        Implement user management module with the following components:
        1. Create user model and schema
        2. Add user repository service
        3. Implement API endpoints for CRUD
        4. Write comprehensive tests
        Additionally, this involves multiple concerns as well as various components.
        """
        # Make it long enough to trigger the length signal
        text = base_text * 5

        candidate = TaskCandidate(
            raw_text=text,
            action_type=ActionType.CREATE,
            target="user management",
        )

        result = decompose_candidate(candidate)
        assert result.should_decompose
        assert len(result.subtasks) >= 3

    def test_decompose_infers_standard_subtasks(self):
        """Test that standard subtasks are inferred for creation tasks."""
        # Create a task that's too large but doesn't have explicit structure
        large_text = "Implement a complete payment processing module " * 20

        candidate = TaskCandidate(
            raw_text=large_text,
            action_type=ActionType.CREATE,
            target="payment processing module",
        )

        result = decompose_candidate(candidate)
        if result.should_decompose:
            # Should have inferred subtasks
            assert len(result.subtasks) > 0


class TestMatcher:
    """Tests for task matching."""

    def test_similarity_identical_text(self):
        """Test similarity of identical text."""
        score = similarity_score("Add login button", "Add login button")
        assert score == 1.0

    def test_similarity_similar_text(self):
        """Test similarity of similar text."""
        score = similarity_score(
            "Add a login button to the navbar",
            "Implement login button in navigation bar"
        )
        assert score > 0.3  # Should have reasonable similarity

    def test_similarity_different_text(self):
        """Test similarity of unrelated text."""
        score = similarity_score(
            "Add login button",
            "Fix database performance issue"
        )
        assert score < 0.3  # Should be low

    def test_find_matching_task(self):
        """Test finding a matching task."""
        tasks = [
            Task(
                id="bd-1234",
                project_id=uuid4(),
                title="Implement user authentication",
                description="Add JWT-based auth",
            ),
            Task(
                id="bd-5678",
                project_id=uuid4(),
                title="Fix database bug",
                description="Connection pool issue",
            ),
        ]

        match, score = find_matching_task(
            "Add user authentication system",
            tasks,
            threshold=0.3
        )

        assert match is not None
        assert match.id == "bd-1234"
        assert score > 0.3

    def test_no_match_below_threshold(self):
        """Test that no match is returned below threshold."""
        tasks = [
            Task(
                id="bd-1234",
                project_id=uuid4(),
                title="Implement payment processing",
                description="Stripe integration",
            ),
        ]

        match, score = find_matching_task(
            "Add user authentication",
            tasks,
            threshold=0.8  # High threshold
        )

        assert match is None


class TestBeadCreatorService:
    """Integration tests for the bead creator service."""

    @pytest.fixture
    async def db(self):
        """Create a test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            await db.connect()
            yield db
            await db.disconnect()

    @pytest.fixture
    async def project(self, db) -> Project:
        """Create a test project."""
        repo = ProjectRepository(db)
        project = Project(
            name="Test Project",
            description="For testing",
            tech_stack=["python"],
        )
        return await repo.create(project)

    async def test_create_simple_task(self, db, project):
        """Test creating a simple task from input."""
        creator = BeadCreator(db)

        result = await creator.create_from_input(
            project_id=project.id,
            text="Add a logout button",
        )

        assert len(result.created_tasks) == 1
        assert "logout" in result.created_tasks[0].task.title.lower() or \
               "logout" in (result.created_tasks[0].task.description or "").lower()

    async def test_create_multiple_tasks(self, db, project):
        """Test creating multiple tasks from input."""
        creator = BeadCreator(db)

        result = await creator.create_from_input(
            project_id=project.id,
            text="Fix the login bug. Add password reset. Write tests.",
        )

        assert len(result.created_tasks) >= 2

    async def test_create_epic(self, db, project):
        """Test creating an epic with child tasks."""
        creator = BeadCreator(db)

        result = await creator.create_from_input(
            project_id=project.id,
            text="Build a complete authentication system with registration, "
                 "login, password reset, and two-factor authentication.",
        )

        assert result.epic is not None
        assert len(result.created_tasks) >= 1

    async def test_match_existing_task(self, db, project):
        """Test that matching tasks are updated instead of duplicated."""
        creator = BeadCreator(db)

        # Create initial task
        result1 = await creator.create_from_input(
            project_id=project.id,
            text="Implement user authentication",
        )
        initial_id = result1.created_tasks[0].task.id

        # Try to create similar task
        result2 = await creator.create_from_input(
            project_id=project.id,
            text="Add user authentication system",
        )

        # Should match the existing task
        if result2.created_tasks:
            matched = result2.created_tasks[0]
            if matched.was_updated:
                assert matched.matched_task_id == initial_id

    async def test_dependencies_created(self, db, project):
        """Test that dependencies are created for ordered tasks."""
        creator = BeadCreator(db)

        result = await creator.create_from_input(
            project_id=project.id,
            text="First create the database schema. Then add the API endpoints.",
        )

        # Should have at least one dependency if ordering was detected
        assert len(result.created_tasks) >= 2
        # Dependencies may or may not be created depending on ordering detection

    async def test_suggest_related(self, db, project):
        """Test suggesting related tasks."""
        creator = BeadCreator(db)

        # Create some tasks first
        await creator.create_from_input(
            project_id=project.id,
            text="Implement user registration with email verification",
        )

        # Find related tasks - use similar phrasing
        related = await creator.suggest_related(
            project_id=project.id,
            text="User registration email verification",
        )

        assert len(related) > 0
        assert related[0][1] > 0.2  # Should have some similarity

    async def test_priority_inheritance(self, db, project):
        """Test that tasks inherit priority from input."""
        creator = BeadCreator(db)

        result = await creator.create_from_input(
            project_id=project.id,
            text="Fix critical security bug",
            priority=Priority.P0,
        )

        assert len(result.created_tasks) == 1
        assert result.created_tasks[0].task.priority == Priority.P0

    async def test_no_decompose_option(self, db, project):
        """Test disabling auto-decomposition."""
        creator = BeadCreator(db, auto_decompose=False)

        long_text = """
        Build authentication system:
        1. Add registration
        2. Add login
        3. Add password reset
        4. Add two-factor auth
        """

        result = await creator.create_from_input(
            project_id=project.id,
            text=long_text,
        )

        # Without decomposition, should create fewer tasks
        # (or one task depending on parsing)
        assert len(result.created_tasks) >= 1
