"""Tests for RLM summarization."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from ringmaster.db import ChatRepository, Database, ProjectRepository
from ringmaster.domain import ChatMessage, Project, Summary
from ringmaster.enricher.rlm import (
    CompressionConfig,
    RLMSummarizer,
)


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        await database.connect()
        yield database
        await database.disconnect()


@pytest.fixture
async def chat_repo(db):
    """Create a chat repository."""
    return ChatRepository(db)


@pytest.fixture
async def project(db):
    """Create a test project."""
    repo = ProjectRepository(db)
    proj = Project(
        name="Test Project",
        description="A test project",
    )
    return await repo.create(proj)


class TestChatRepository:
    """Tests for ChatRepository."""

    async def test_create_and_get_message(self, chat_repo, project):
        """Test creating and retrieving a message."""
        message = ChatMessage(
            project_id=project.id,
            role="user",
            content="Hello, world!",
        )
        created = await chat_repo.create_message(message)

        assert created.id is not None
        assert created.content == "Hello, world!"
        assert created.role == "user"

    async def test_get_messages(self, chat_repo, project):
        """Test getting messages for a project."""
        # Create several messages
        for i in range(5):
            await chat_repo.create_message(
                ChatMessage(
                    project_id=project.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Message {i}",
                )
            )

        messages = await chat_repo.get_messages(project.id)
        assert len(messages) == 5
        assert messages[0].content == "Message 0"
        assert messages[4].content == "Message 4"

    async def test_get_recent_messages(self, chat_repo, project):
        """Test getting recent messages."""
        # Create 10 messages
        for i in range(10):
            await chat_repo.create_message(
                ChatMessage(
                    project_id=project.id,
                    role="user",
                    content=f"Message {i}",
                )
            )

        recent = await chat_repo.get_recent_messages(project.id, count=3)
        assert len(recent) == 3
        # Should be in chronological order
        assert recent[0].content == "Message 7"
        assert recent[1].content == "Message 8"
        assert recent[2].content == "Message 9"

    async def test_get_message_count(self, chat_repo, project):
        """Test getting message count."""
        # Initially zero
        count = await chat_repo.get_message_count(project.id)
        assert count == 0

        # Add messages
        for i in range(5):
            await chat_repo.create_message(
                ChatMessage(project_id=project.id, role="user", content=f"Msg {i}")
            )

        count = await chat_repo.get_message_count(project.id)
        assert count == 5

    async def test_create_and_get_summary(self, chat_repo, project):
        """Test creating and retrieving summaries."""
        summary = Summary(
            project_id=project.id,
            message_range_start=1,
            message_range_end=10,
            summary="Discussion about features",
            key_decisions=["Use Python", "Use SQLite"],
        )
        created = await chat_repo.create_summary(summary)

        assert created.id is not None
        assert created.summary == "Discussion about features"
        assert len(created.key_decisions) == 2

        # Retrieve summaries
        summaries = await chat_repo.get_summaries(project.id)
        assert len(summaries) == 1
        assert summaries[0].key_decisions == ["Use Python", "Use SQLite"]


class TestRLMSummarizer:
    """Tests for RLMSummarizer."""

    async def test_empty_history(self, db):
        """Test with no chat history (non-existent project)."""
        summarizer = RLMSummarizer(db)
        context = await summarizer.get_history_context(uuid4())

        assert context.total_messages == 0
        assert context.recent_messages == []
        assert context.summaries == []

    async def test_few_messages_no_summary(self, db, chat_repo, project):
        """Test with few messages - no summarization needed."""
        # Create 5 messages (below summary threshold)
        for i in range(5):
            await chat_repo.create_message(
                ChatMessage(
                    project_id=project.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Test message {i}",
                )
            )

        summarizer = RLMSummarizer(
            db,
            config=CompressionConfig(
                recent_verbatim=10,
                summary_threshold=20,
            ),
        )
        context = await summarizer.get_history_context(project.id)

        assert context.total_messages == 5
        assert len(context.recent_messages) == 5
        assert len(context.summaries) == 0  # Below threshold

    async def test_summarize_older_messages(self, db, chat_repo, project):
        """Test that older messages get summarized."""
        # Create 30 messages (above threshold)
        for i in range(30):
            await chat_repo.create_message(
                ChatMessage(
                    project_id=project.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Test message {i} about auth.py file",
                )
            )

        config = CompressionConfig(
            recent_verbatim=10,
            summary_threshold=15,
            chunk_size=10,
        )
        summarizer = RLMSummarizer(db, config)
        context = await summarizer.get_history_context(project.id)

        assert context.total_messages == 30
        assert len(context.recent_messages) == 10  # Last 10 verbatim
        # Should have summaries for older messages
        assert len(context.summaries) > 0

    async def test_decision_extraction(self, db, chat_repo, project):
        """Test that decisions are extracted from messages."""
        # Create messages with decisions
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="user",
                content="Let's discuss the database choice.",
            )
        )
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="assistant",
                content="We decided to use PostgreSQL for the main database.",
            )
        )
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="user",
                content="What about caching?",
            )
        )
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="assistant",
                content="We'll use Redis for caching. Going with JSON serialization.",
            )
        )

        summarizer = RLMSummarizer(db)
        context = await summarizer.get_history_context(project.id)

        # Should have extracted decisions
        assert len(context.key_decisions) > 0
        # Check for expected decisions
        decisions_text = " ".join(context.key_decisions).lower()
        assert "postgresql" in decisions_text or "redis" in decisions_text

    async def test_format_for_prompt(self, db, chat_repo, project):
        """Test formatting context for prompt inclusion."""
        # Create some messages
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="user",
                content="What should we build?",
            )
        )
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="assistant",
                content="We decided to build a REST API.",
            )
        )

        summarizer = RLMSummarizer(db)
        context = await summarizer.get_history_context(project.id)
        formatted = summarizer.format_for_prompt(context)

        assert "## Conversation History" in formatted
        assert "### Recent Messages" in formatted
        assert "What should we build?" in formatted
        assert "REST API" in formatted

    async def test_token_estimation(self, db, chat_repo, project):
        """Test token count estimation."""
        # Create messages with known content length
        content = "A" * 400  # ~100 tokens
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="user",
                content=content,
            )
        )

        summarizer = RLMSummarizer(db)
        context = await summarizer.get_history_context(project.id)

        # Should estimate ~100 tokens (400 chars / 4)
        assert context.estimated_tokens >= 90
        assert context.estimated_tokens <= 110


class TestHistoryContextStage:
    """Tests for HistoryContextStage."""

    async def test_no_database_returns_none(self):
        """Test that stage returns None when no database configured."""
        from ringmaster.domain import Task
        from ringmaster.enricher.stages import HistoryContextStage

        stage = HistoryContextStage(db=None)
        task = Task(
            id="task-123",
            project_id=uuid4(),
            title="Test Task",
        )
        project = Project(name="Test", description="Test project")

        result = await stage.process(task, project)
        assert result is None

    async def test_empty_history_returns_none(self, db, project):
        """Test that stage returns None when no chat history."""
        from ringmaster.domain import Task
        from ringmaster.enricher.stages import HistoryContextStage

        stage = HistoryContextStage(db=db)
        task = Task(
            id="task-123",
            project_id=project.id,
            title="Test Task",
        )

        # No messages in database, should return None
        result = await stage.process(task, project)
        assert result is None

    async def test_with_messages_returns_stage_result(self, db, chat_repo, project):
        """Test that stage returns StageResult when messages exist."""
        from ringmaster.domain import Task
        from ringmaster.enricher.stages import HistoryContextStage, StageResult

        # Create some chat messages
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="user",
                content="What should we build?",
            )
        )
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="assistant",
                content="We decided to build a REST API.",
            )
        )

        stage = HistoryContextStage(db=db)
        task = Task(
            id="task-123",
            project_id=project.id,
            title="Test Task",
        )

        result = await stage.process(task, project)

        assert result is not None
        assert isinstance(result, StageResult)
        assert "## Conversation History" in result.content
        assert "What should we build?" in result.content
        assert result.tokens_estimate > 0
        assert result.sources is not None
        assert len(result.sources) > 0

    async def test_stage_name(self, db):
        """Test that stage name is correct."""
        from ringmaster.enricher.stages import HistoryContextStage

        stage = HistoryContextStage(db=db)
        assert stage.name == "history_context"

    async def test_task_scoped_messages(self, db, chat_repo, project):
        """Test that stage respects task_id filtering."""
        from ringmaster.domain import Task
        from ringmaster.enricher.stages import HistoryContextStage

        # Create project-wide message (no task_id)
        await chat_repo.create_message(
            ChatMessage(
                project_id=project.id,
                role="user",
                content="This is a project-wide message",
            )
        )

        stage = HistoryContextStage(db=db)
        task = Task(
            id="task-specific-123",
            project_id=project.id,
            title="Test Task",
        )

        result = await stage.process(task, project)

        # Should return context from project-wide messages
        assert result is not None
        assert result.tokens_estimate > 0
