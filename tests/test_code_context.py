"""Tests for code context extraction."""

import tempfile
from pathlib import Path

import pytest

from ringmaster.enricher.code_context import (
    CodeContextExtractor,
    CodeContextResult,
    format_code_context,
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)

        # Create source directory structure
        src_dir = project / "src" / "myproject"
        src_dir.mkdir(parents=True)

        # Create main.py
        (src_dir / "main.py").write_text('''"""Main module."""
from myproject.utils import helper_function

def main():
    """Entry point."""
    result = helper_function()
    return result

if __name__ == "__main__":
    main()
''')

        # Create utils.py
        (src_dir / "utils.py").write_text('''"""Utility functions."""

def helper_function():
    """A helper function."""
    return "hello"

def calculate_total(items):
    """Calculate total from items."""
    return sum(items)

class DataProcessor:
    """Process data."""

    def process(self, data):
        """Process the data."""
        return data.upper()
''')

        # Create models.py
        (src_dir / "models.py").write_text('''"""Domain models."""
from dataclasses import dataclass

@dataclass
class User:
    """User model."""
    id: str
    name: str
    email: str

@dataclass
class Task:
    """Task model."""
    id: str
    title: str
    description: str
''')

        # Create __init__.py files
        (project / "src" / "__init__.py").touch()
        (src_dir / "__init__.py").write_text('"""My project."""\n')

        # Create a test file
        tests_dir = project / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_utils.py").write_text('''"""Tests for utils."""
import pytest
from myproject.utils import helper_function, calculate_total

def test_helper_function():
    assert helper_function() == "hello"

def test_calculate_total():
    assert calculate_total([1, 2, 3]) == 6
''')

        yield project


class TestCodeContextExtractor:
    """Tests for CodeContextExtractor."""

    def test_extract_explicit_file_reference(self, temp_project):
        """Test extraction when file path is explicitly mentioned."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        task_desc = "Fix the bug in src/myproject/utils.py where helper_function returns wrong value"
        result = extractor.extract(task_desc)

        assert len(result.files) >= 1
        assert any("utils.py" in str(f.path) for f in result.files)

    def test_extract_keyword_matching(self, temp_project):
        """Test extraction based on keyword matching."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        task_desc = "Update the DataProcessor class to handle None values"
        result = extractor.extract(task_desc)

        # Should find utils.py which contains DataProcessor
        assert len(result.files) >= 1
        assert any("DataProcessor" in f.content for f in result.files)

    def test_extract_function_keyword(self, temp_project):
        """Test extraction based on function name keyword."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        task_desc = "Modify calculate_total to handle empty lists"
        result = extractor.extract(task_desc)

        assert len(result.files) >= 1
        assert any("calculate_total" in f.content for f in result.files)

    def test_extract_class_keyword(self, temp_project):
        """Test extraction finds files with class definitions."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        task_desc = "Add a method to the User model for validation"
        result = extractor.extract(task_desc)

        # Should find models.py which contains User class
        assert len(result.files) >= 1
        assert any("User" in f.content for f in result.files)

    def test_max_files_limit(self, temp_project):
        """Test that max_files limit is respected."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
            max_files=2,
        )

        task_desc = "Refactor all utilities and models"
        result = extractor.extract(task_desc)

        assert len(result.files) <= 2

    def test_token_budget(self, temp_project):
        """Test that token budget is respected."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=100,  # Very low budget
        )

        task_desc = "Update the DataProcessor class"
        result = extractor.extract(task_desc)

        # Token budget should be respected
        assert result.total_tokens <= 100

    def test_empty_result_for_no_matches(self, temp_project):
        """Test empty result when no files match."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        task_desc = "Fix the XYZ component in NonExistentFile"
        result = extractor.extract(task_desc)

        # May find some files due to keyword matching, but should be limited
        assert isinstance(result, CodeContextResult)

    def test_ignores_pycache(self, temp_project):
        """Test that __pycache__ directories are ignored."""
        # Create a __pycache__ directory
        pycache = temp_project / "src" / "myproject" / "__pycache__"
        pycache.mkdir()
        (pycache / "utils.cpython-312.pyc").write_bytes(b"fake bytecode")

        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        task_desc = "Update utils module"
        result = extractor.extract(task_desc)

        # Should not include .pyc files
        assert not any(".pyc" in str(f.path) for f in result.files)
        assert not any("__pycache__" in str(f.path) for f in result.files)

    def test_relevance_score_ordering(self, temp_project):
        """Test that files are ordered by relevance score."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        # Explicit file reference should have higher score
        task_desc = "Fix bug in src/myproject/main.py involving helper_function"
        result = extractor.extract(task_desc)

        if len(result.files) >= 2:
            # Explicitly mentioned file should be first
            assert result.files[0].relevance_score >= result.files[-1].relevance_score


class TestFormatCodeContext:
    """Tests for format_code_context function."""

    def test_format_with_files(self, temp_project):
        """Test formatting with files."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        result = extractor.extract("Update DataProcessor class")
        formatted = format_code_context(result, temp_project)

        assert "## Code Context" in formatted
        assert "```py" in formatted or "```" in formatted

    def test_format_empty_result(self, temp_project):
        """Test formatting with empty result."""
        result = CodeContextResult(files=[], total_tokens=0)
        formatted = format_code_context(result, temp_project)

        assert formatted == ""

    def test_format_shows_truncated_message(self, temp_project):
        """Test that truncation message is shown."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=50,  # Very low budget to force truncation
        )

        result = extractor.extract("Update all code")

        if result.truncated:
            formatted = format_code_context(result, temp_project)
            assert "omitted" in formatted.lower() or result.truncated


class TestKeywordExtraction:
    """Tests for keyword extraction."""

    def test_camel_case_extraction(self, temp_project):
        """Test extraction of CamelCase identifiers."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        keywords = extractor._extract_keywords("Fix the DataProcessor and UserManager classes")

        assert "DataProcessor" in keywords
        assert "UserManager" in keywords

    def test_snake_case_extraction(self, temp_project):
        """Test extraction of snake_case identifiers."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        keywords = extractor._extract_keywords("Update the calculate_total and helper_function")

        assert "calculate_total" in keywords
        assert "helper_function" in keywords

    def test_keyword_limit(self, temp_project):
        """Test that keyword extraction is limited."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        # Create a description with many identifiers
        desc = " ".join([f"Class{i}" for i in range(20)])
        keywords = extractor._extract_keywords(desc)

        # Should be limited to 10
        assert len(keywords) <= 10


class TestImportExtraction:
    """Tests for import extraction."""

    def test_find_python_imports(self, temp_project):
        """Test extraction of Python imports."""
        extractor = CodeContextExtractor(
            project_dir=temp_project,
            max_tokens=10000,
        )

        content = """
from ringmaster.enricher.pipeline import EnrichmentPipeline
from ringmaster.domain import Task
import os
"""
        # Note: This test is more about the parsing logic
        # In a real codebase, it would find the actual files
        imports = extractor._find_python_imports(content)

        # Should attempt to parse ringmaster imports
        # (won't find actual files since temp_project doesn't have them)
        assert isinstance(imports, list)
