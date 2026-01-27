"""Documentation context extraction for enrichment pipeline.

Per docs/04-context-enrichment.md section 3, this module extracts:
- Project description
- Goals / roadmap
- ADRs (Architecture Decision Records)
- Coding conventions
- API specifications
- Library documentation

The documentation context is always relevant for tasks that need to understand
the project's design decisions and conventions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Common documentation file patterns
DOC_PATTERNS = {
    "readme": [
        "README.md",
        "README",
        "readme.md",
        "README.rst",
        "README.txt",
    ],
    "contributing": [
        "CONTRIBUTING.md",
        "CONTRIBUTING",
        "contributing.md",
    ],
    "conventions": [
        "CONVENTIONS.md",
        "CODING_CONVENTIONS.md",
        "STYLE_GUIDE.md",
        "STYLEGUIDE.md",
        "conventions.md",
        ".editorconfig",
    ],
    "architecture": [
        "ARCHITECTURE.md",
        "architecture.md",
        "DESIGN.md",
        "design.md",
    ],
    "api": [
        "API.md",
        "api.md",
        "openapi.yaml",
        "openapi.yml",
        "swagger.yaml",
        "swagger.yml",
        "openapi.json",
        "swagger.json",
    ],
}

# ADR directory patterns
ADR_DIRS = [
    "docs/adr",
    "docs/adrs",
    "doc/adr",
    "doc/adrs",
    "adr",
    "adrs",
    "docs/decisions",
    "decisions",
    "architecture/decisions",
]

# Documentation directory patterns
DOC_DIRS = [
    "docs",
    "doc",
    "documentation",
    "wiki",
]


@dataclass
class DocFile:
    """A documentation file with content."""

    path: Path
    doc_type: str  # readme, adr, conventions, api, etc.
    content: str
    tokens_estimate: int = 0
    relevance_score: float = 1.0


@dataclass
class DocumentationContextResult:
    """Result of documentation context extraction."""

    files: list[DocFile] = field(default_factory=list)
    total_tokens: int = 0
    summary: str = ""


class DocumentationContextExtractor:
    """Extracts relevant documentation files for task context.

    Documentation context includes:
    - Project README and goals
    - Architecture Decision Records (ADRs)
    - Coding conventions and style guides
    - API specifications

    Uses keyword matching to filter ADRs and API specs
    to only include those relevant to the current task.
    """

    # Keywords that indicate API-related tasks
    API_KEYWORDS = {
        "api", "endpoint", "route", "rest", "graphql",
        "request", "response", "http", "https", "controller",
        "handler", "middleware", "swagger", "openapi",
    }

    # Keywords that indicate architecture/design tasks
    ARCHITECTURE_KEYWORDS = {
        "architecture", "design", "pattern", "structure",
        "refactor", "migration", "module", "component",
        "service", "layer", "interface", "abstraction",
    }

    def __init__(
        self,
        project_dir: Path,
        max_tokens: int = 3000,
        max_files: int = 8,
        max_file_lines: int = 500,
        include_adrs: bool = True,
        include_api_specs: bool = True,
    ):
        """Initialize the documentation extractor.

        Args:
            project_dir: Root directory of the project.
            max_tokens: Maximum tokens to allocate for documentation context.
            max_files: Maximum number of documentation files to include.
            max_file_lines: Maximum lines per file to include.
            include_adrs: Whether to include ADRs.
            include_api_specs: Whether to include API specifications.
        """
        self.project_dir = Path(project_dir)
        self.max_tokens = max_tokens
        self.max_files = max_files
        self.max_file_lines = max_file_lines
        self.include_adrs = include_adrs
        self.include_api_specs = include_api_specs

    def extract(self, task_description: str) -> DocumentationContextResult:
        """Extract relevant documentation for a task.

        Args:
            task_description: The task description to match against.

        Returns:
            DocumentationContextResult with matching documentation files.
        """
        result = DocumentationContextResult()
        task_lower = task_description.lower()

        # Extract keywords from task
        task_keywords = self._extract_keywords(task_description)

        # Always include README if present
        readme = self._find_readme()
        if readme:
            result.files.append(readme)

        # Always include conventions if present
        conventions = self._find_conventions()
        if conventions:
            result.files.extend(conventions)

        # Include ADRs if task matches architecture keywords
        if self.include_adrs:
            adrs = self._find_adrs(task_keywords, task_lower)
            result.files.extend(adrs)

        # Include API specs if task is API-related
        if self.include_api_specs and self._is_api_related(task_lower):
            api_specs = self._find_api_specs()
            result.files.extend(api_specs)

        # Include architecture docs if task is architecture-related
        if self._is_architecture_related(task_lower):
            arch_docs = self._find_architecture_docs()
            result.files.extend(arch_docs)

        # Sort by relevance and limit
        result.files.sort(key=lambda f: f.relevance_score, reverse=True)
        result.files = result.files[: self.max_files]

        # Calculate total tokens
        result.total_tokens = sum(f.tokens_estimate for f in result.files)

        # Truncate if over budget
        if result.total_tokens > self.max_tokens:
            result = self._truncate_to_budget(result)

        # Build summary
        result.summary = self._build_summary(result)

        return result

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract relevant keywords from text."""
        words = set(re.findall(r'\b[a-z]+\b', text.lower()))
        return words

    def _find_readme(self) -> DocFile | None:
        """Find the project README."""
        for name in DOC_PATTERNS["readme"]:
            path = self.project_dir / name
            if path.exists() and path.is_file():
                try:
                    content = self._read_file(path)
                    return DocFile(
                        path=path,
                        doc_type="readme",
                        content=content,
                        tokens_estimate=len(content) // 4,
                        relevance_score=1.0,
                    )
                except Exception as e:
                    logger.warning("Failed to read README %s: %s", path, e)
        return None

    def _find_conventions(self) -> list[DocFile]:
        """Find coding conventions and style guides."""
        files = []
        for name in DOC_PATTERNS["conventions"]:
            path = self.project_dir / name
            if path.exists() and path.is_file():
                try:
                    content = self._read_file(path)
                    files.append(DocFile(
                        path=path,
                        doc_type="conventions",
                        content=content,
                        tokens_estimate=len(content) // 4,
                        relevance_score=0.9,
                    ))
                except Exception as e:
                    logger.warning("Failed to read conventions %s: %s", path, e)
        return files

    def _find_adrs(self, task_keywords: set[str], task_lower: str) -> list[DocFile]:
        """Find ADRs relevant to the task."""
        files = []

        for adr_dir in ADR_DIRS:
            adr_path = self.project_dir / adr_dir
            if not adr_path.exists() or not adr_path.is_dir():
                continue

            # Find all markdown files in ADR directory
            for md_file in adr_path.glob("*.md"):
                try:
                    content = self._read_file(md_file)

                    # Score relevance based on keyword overlap
                    score = self._score_adr_relevance(
                        md_file.stem,
                        content,
                        task_keywords,
                        task_lower,
                    )

                    if score >= 0.3:  # Only include if relevant
                        files.append(DocFile(
                            path=md_file,
                            doc_type="adr",
                            content=content,
                            tokens_estimate=len(content) // 4,
                            relevance_score=score,
                        ))
                except Exception as e:
                    logger.warning("Failed to read ADR %s: %s", md_file, e)

        return files

    def _score_adr_relevance(
        self,
        filename: str,
        content: str,
        task_keywords: set[str],
        task_lower: str,
    ) -> float:
        """Score how relevant an ADR is to the task."""
        score = 0.0

        # Check if task explicitly mentions the ADR
        filename_lower = filename.lower().replace("-", " ").replace("_", " ")
        if any(word in task_lower for word in filename_lower.split() if len(word) > 3):
            score += 0.5

        # Keyword overlap with content
        content_keywords = self._extract_keywords(content)
        keyword_overlap = task_keywords & content_keywords
        score += min(len(keyword_overlap) / 5, 0.4)

        # Check title/heading relevance
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).lower()
            title_words = set(title.split())
            task_words = set(task_lower.split())
            if title_words & task_words:
                score += 0.2

        return min(score, 1.0)

    def _find_api_specs(self) -> list[DocFile]:
        """Find API specifications."""
        files = []

        for name in DOC_PATTERNS["api"]:
            path = self.project_dir / name
            if path.exists() and path.is_file():
                try:
                    content = self._read_file(path)
                    files.append(DocFile(
                        path=path,
                        doc_type="api",
                        content=content,
                        tokens_estimate=len(content) // 4,
                        relevance_score=0.8,
                    ))
                except Exception as e:
                    logger.warning("Failed to read API spec %s: %s", path, e)

        # Also check docs directories
        for doc_dir in DOC_DIRS:
            doc_path = self.project_dir / doc_dir
            if not doc_path.exists():
                continue

            for name in DOC_PATTERNS["api"]:
                path = doc_path / name
                if path.exists() and path.is_file():
                    try:
                        content = self._read_file(path)
                        files.append(DocFile(
                            path=path,
                            doc_type="api",
                            content=content,
                            tokens_estimate=len(content) // 4,
                            relevance_score=0.8,
                        ))
                    except Exception as e:
                        logger.warning("Failed to read API spec %s: %s", path, e)

        return files

    def _find_architecture_docs(self) -> list[DocFile]:
        """Find architecture documentation."""
        files = []

        for name in DOC_PATTERNS["architecture"]:
            path = self.project_dir / name
            if path.exists() and path.is_file():
                try:
                    content = self._read_file(path)
                    files.append(DocFile(
                        path=path,
                        doc_type="architecture",
                        content=content,
                        tokens_estimate=len(content) // 4,
                        relevance_score=0.85,
                    ))
                except Exception as e:
                    logger.warning("Failed to read architecture doc %s: %s", path, e)

        # Also check docs directories
        for doc_dir in DOC_DIRS:
            doc_path = self.project_dir / doc_dir
            if not doc_path.exists():
                continue

            for name in DOC_PATTERNS["architecture"]:
                path = doc_path / name
                if path.exists() and path.is_file():
                    try:
                        content = self._read_file(path)
                        files.append(DocFile(
                            path=path,
                            doc_type="architecture",
                            content=content,
                            tokens_estimate=len(content) // 4,
                            relevance_score=0.85,
                        ))
                    except Exception as e:
                        logger.warning("Failed to read architecture doc %s: %s", path, e)

        return files

    def _is_api_related(self, task_lower: str) -> bool:
        """Check if task is API-related."""
        return any(kw in task_lower for kw in self.API_KEYWORDS)

    def _is_architecture_related(self, task_lower: str) -> bool:
        """Check if task is architecture-related."""
        return any(kw in task_lower for kw in self.ARCHITECTURE_KEYWORDS)

    def _read_file(self, path: Path) -> str:
        """Read file content with line limiting."""
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) > self.max_file_lines:
                    lines = lines[: self.max_file_lines]
                    lines.append("\n... (truncated)\n")
                return "".join(lines)
        except UnicodeDecodeError:
            # Binary file
            return ""

    def _truncate_to_budget(
        self,
        result: DocumentationContextResult,
    ) -> DocumentationContextResult:
        """Truncate files to fit within token budget."""
        budget_remaining = self.max_tokens
        truncated_files = []

        for doc_file in result.files:
            if doc_file.tokens_estimate <= budget_remaining:
                truncated_files.append(doc_file)
                budget_remaining -= doc_file.tokens_estimate
            elif budget_remaining > 100:
                # Truncate content to fit remaining budget
                max_chars = budget_remaining * 4
                truncated_content = doc_file.content[:max_chars] + "\n... (truncated)"
                truncated_files.append(DocFile(
                    path=doc_file.path,
                    doc_type=doc_file.doc_type,
                    content=truncated_content,
                    tokens_estimate=budget_remaining,
                    relevance_score=doc_file.relevance_score,
                ))
                break

        result.files = truncated_files
        result.total_tokens = sum(f.tokens_estimate for f in truncated_files)
        return result

    def _build_summary(self, result: DocumentationContextResult) -> str:
        """Build a summary of documentation context."""
        parts = []
        types_found = {f.doc_type for f in result.files}

        if "readme" in types_found:
            parts.append("README")
        if "conventions" in types_found:
            parts.append("coding conventions")
        if "adr" in types_found:
            adr_count = sum(1 for f in result.files if f.doc_type == "adr")
            parts.append(f"{adr_count} ADR(s)")
        if "api" in types_found:
            parts.append("API spec")
        if "architecture" in types_found:
            parts.append("architecture docs")

        if parts:
            return f"Documentation context: {', '.join(parts)}"
        return "No documentation context found"


def format_documentation_context(
    result: DocumentationContextResult,
    project_dir: Path,
) -> str:
    """Format documentation context for prompt inclusion.

    Args:
        result: The extraction result.
        project_dir: Project directory for relative paths.

    Returns:
        Formatted markdown string for prompt inclusion.
    """
    if not result.files:
        return ""

    parts = ["## Documentation Context", ""]

    for doc_file in result.files:
        rel_path = doc_file.path.relative_to(project_dir)
        type_label = doc_file.doc_type.upper()

        parts.append(f"### [{type_label}] {rel_path}")
        parts.append("```")
        parts.append(doc_file.content.strip())
        parts.append("```")
        parts.append("")

    return "\n".join(parts)
