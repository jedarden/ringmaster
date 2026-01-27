"""Tests for documentation context extraction."""

import tempfile
from pathlib import Path

import pytest

from ringmaster.enricher.documentation_context import (
    DocumentationContextExtractor,
    format_documentation_context,
)


class TestDocumentationContextExtractor:
    """Tests for DocumentationContextExtractor."""

    def test_finds_readme(self, tmp_path: Path):
        """Test finding README file."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n\nThis is a test project.")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement feature")

        assert len(result.files) == 1
        assert result.files[0].doc_type == "readme"
        assert "test project" in result.files[0].content

    def test_finds_conventions(self, tmp_path: Path):
        """Test finding coding conventions file."""
        conventions = tmp_path / "CONVENTIONS.md"
        conventions.write_text("# Coding Conventions\n\nUse 4 spaces.")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement feature")

        assert len(result.files) == 1
        assert result.files[0].doc_type == "conventions"
        assert "4 spaces" in result.files[0].content

    def test_finds_editorconfig(self, tmp_path: Path):
        """Test finding .editorconfig file."""
        editorconfig = tmp_path / ".editorconfig"
        editorconfig.write_text("root = true\n\n[*]\nindent_style = space")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement feature")

        assert len(result.files) == 1
        assert result.files[0].doc_type == "conventions"
        assert "indent_style" in result.files[0].content

    def test_finds_adrs_for_relevant_task(self, tmp_path: Path):
        """Test finding ADRs when task is architecture-related."""
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)

        adr1 = adr_dir / "001-use-jwt.md"
        adr1.write_text("# Use JWT for Authentication\n\nWe decided to use JWT tokens.")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement authentication with jwt tokens")

        # Should find the ADR because it matches keywords
        adr_files = [f for f in result.files if f.doc_type == "adr"]
        assert len(adr_files) == 1
        assert "JWT" in adr_files[0].content

    def test_filters_irrelevant_adrs(self, tmp_path: Path):
        """Test that irrelevant ADRs are filtered out."""
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)

        # ADR about unrelated topic
        adr1 = adr_dir / "001-database-choice.md"
        adr1.write_text("# Database Choice\n\nWe use PostgreSQL.")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        # Task about frontend, shouldn't match database ADR
        result = extractor.extract("implement button component")

        adr_files = [f for f in result.files if f.doc_type == "adr"]
        assert len(adr_files) == 0

    def test_finds_api_spec_for_api_task(self, tmp_path: Path):
        """Test finding API specs for API-related tasks."""
        api_spec = tmp_path / "openapi.yaml"
        api_spec.write_text("openapi: 3.0.0\npaths:\n  /users:\n    get:")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement new api endpoint for users")

        api_files = [f for f in result.files if f.doc_type == "api"]
        assert len(api_files) == 1
        assert "/users" in api_files[0].content

    def test_no_api_spec_for_non_api_task(self, tmp_path: Path):
        """Test that API specs are excluded for non-API tasks."""
        api_spec = tmp_path / "openapi.yaml"
        api_spec.write_text("openapi: 3.0.0\npaths:\n  /users:\n    get:")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("fix typo in readme")

        api_files = [f for f in result.files if f.doc_type == "api"]
        assert len(api_files) == 0

    def test_finds_architecture_docs_for_refactor_task(self, tmp_path: Path):
        """Test finding architecture docs for architecture-related tasks."""
        arch_doc = tmp_path / "ARCHITECTURE.md"
        arch_doc.write_text("# Architecture\n\n## Modules\n\nService layer pattern.")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("refactor service layer pattern")

        arch_files = [f for f in result.files if f.doc_type == "architecture"]
        assert len(arch_files) == 1

    def test_respects_max_files_limit(self, tmp_path: Path):
        """Test that max_files limit is respected."""
        # Create many files
        readme = tmp_path / "README.md"
        readme.write_text("# Project")

        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        for i in range(10):
            adr = adr_dir / f"00{i}-decision.md"
            adr.write_text(f"# Decision {i}\n\nPattern architecture design.")

        extractor = DocumentationContextExtractor(
            project_dir=tmp_path,
            max_files=3,
        )
        result = extractor.extract("implement architecture pattern design")

        assert len(result.files) <= 3

    def test_respects_max_tokens_budget(self, tmp_path: Path):
        """Test that token budget is respected."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n" + "Content. " * 1000)  # ~3000 tokens

        extractor = DocumentationContextExtractor(
            project_dir=tmp_path,
            max_tokens=500,
        )
        result = extractor.extract("implement feature")

        assert result.total_tokens <= 500

    def test_truncates_long_files(self, tmp_path: Path):
        """Test that long files are truncated."""
        readme = tmp_path / "README.md"
        lines = ["Line " + str(i) for i in range(1000)]
        readme.write_text("\n".join(lines))

        extractor = DocumentationContextExtractor(
            project_dir=tmp_path,
            max_file_lines=100,
        )
        result = extractor.extract("implement feature")

        assert "truncated" in result.files[0].content

    def test_handles_missing_description(self, tmp_path: Path):
        """Test handling empty task description."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("")

        # Should still find README (always included)
        assert len(result.files) == 1

    def test_multiple_doc_types_combined(self, tmp_path: Path):
        """Test combining multiple documentation types."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project")

        conventions = tmp_path / "CONVENTIONS.md"
        conventions.write_text("# Conventions")

        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "001-api.md"
        adr.write_text("# API Architecture\n\nREST endpoints.")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement api endpoint")

        types_found = {f.doc_type for f in result.files}
        assert "readme" in types_found
        assert "conventions" in types_found
        # ADR should be found due to "api" keyword match
        assert "adr" in types_found

    def test_builds_summary(self, tmp_path: Path):
        """Test summary building."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project")

        conventions = tmp_path / "CONVENTIONS.md"
        conventions.write_text("# Conventions")

        extractor = DocumentationContextExtractor(project_dir=tmp_path)
        result = extractor.extract("implement feature")

        assert "README" in result.summary
        assert "coding conventions" in result.summary


class TestFormatDocumentationContext:
    """Tests for format_documentation_context."""

    def test_formats_readme(self, tmp_path: Path):
        """Test formatting README."""
        extractor = DocumentationContextExtractor(project_dir=tmp_path)

        # Create a mock result
        from ringmaster.enricher.documentation_context import (
            DocFile,
            DocumentationContextResult,
        )

        result = DocumentationContextResult(
            files=[
                DocFile(
                    path=tmp_path / "README.md",
                    doc_type="readme",
                    content="# Project\n\nDescription.",
                    tokens_estimate=10,
                ),
            ],
            total_tokens=10,
        )

        formatted = format_documentation_context(result, tmp_path)

        assert "## Documentation Context" in formatted
        assert "[README]" in formatted
        assert "README.md" in formatted
        assert "# Project" in formatted

    def test_empty_result_returns_empty(self, tmp_path: Path):
        """Test that empty result returns empty string."""
        from ringmaster.enricher.documentation_context import (
            DocumentationContextResult,
        )

        result = DocumentationContextResult()
        formatted = format_documentation_context(result, tmp_path)

        assert formatted == ""


class TestDocumentationContextStage:
    """Integration tests for DocumentationContextStage."""

    @pytest.mark.asyncio
    async def test_stage_processes_task(self, tmp_path: Path):
        """Test stage processing with real task."""
        import uuid

        readme = tmp_path / "README.md"
        readme.write_text("# Test Project")

        from ringmaster.domain import Priority, Project, Task, TaskStatus, TaskType
        from ringmaster.enricher.stages import DocumentationContextStage

        project_id = uuid.uuid4()
        task = Task(
            id="task-1",
            title="Implement feature",
            description="Add a new feature",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
            project_id=project_id,
        )
        project = Project(id=project_id, name="Test Project")

        stage = DocumentationContextStage(project_dir=tmp_path)
        result = await stage.process(task, project)

        assert result is not None
        assert "README" in result.content
        assert result.tokens_estimate > 0

    @pytest.mark.asyncio
    async def test_stage_returns_none_for_no_docs(self, tmp_path: Path):
        """Test stage returns None when no documentation found."""
        import uuid

        from ringmaster.domain import Priority, Project, Task, TaskStatus, TaskType
        from ringmaster.enricher.stages import DocumentationContextStage

        project_id = uuid.uuid4()
        task = Task(
            id="task-1",
            title="Implement feature",
            description="Add a new feature",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
            project_id=project_id,
        )
        project = Project(id=project_id, name="Test Project")

        stage = DocumentationContextStage(project_dir=tmp_path)
        result = await stage.process(task, project)

        assert result is None

    @pytest.mark.asyncio
    async def test_stage_name(self, tmp_path: Path):
        """Test stage has correct name."""
        from ringmaster.enricher.stages import DocumentationContextStage

        stage = DocumentationContextStage(project_dir=tmp_path)
        assert stage.name == "documentation_context"
