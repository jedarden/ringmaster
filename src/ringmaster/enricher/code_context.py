"""Code context extraction for task enrichment.

Based on docs/04-context-enrichment.md:
- Extracts file references from task descriptions
- Finds semantically related files using keyword matching
- Includes import dependencies and type definitions
- Applies relevance scoring and token budgeting
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Common code file extensions
CODE_EXTENSIONS = {
    ".py", ".rs", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".java", ".rb", ".c", ".cpp", ".h",
    ".cs", ".swift", ".kt", ".scala", ".clj",
}

# Default patterns to ignore
IGNORE_PATTERNS = {
    "__pycache__",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "target",
    "dist",
    "build",
    ".next",
    "coverage",
}


@dataclass
class FileContext:
    """A file included in code context."""

    path: Path
    content: str
    relevance_score: float
    match_reason: str


@dataclass
class CodeContextResult:
    """Result of code context extraction."""

    files: list[FileContext] = field(default_factory=list)
    total_tokens: int = 0
    truncated: bool = False


class CodeContextExtractor:
    """Extracts relevant code files for a task.

    The extractor uses multiple signals to find relevant files:
    1. Explicit mentions - file paths in the task description
    2. Keyword matching - function/class/module names
    3. Import dependencies - files imported by explicit mentions
    """

    def __init__(
        self,
        project_dir: Path,
        max_tokens: int = 12000,
        max_files: int = 10,
        max_file_lines: int = 500,
    ):
        self.project_dir = project_dir
        self.max_tokens = max_tokens
        self.max_files = max_files
        self.max_file_lines = max_file_lines

    def extract(self, task_description: str) -> CodeContextResult:
        """Extract relevant code context for a task.

        Args:
            task_description: The task description to analyze.

        Returns:
            CodeContextResult with relevant files and metadata.
        """
        result = CodeContextResult()

        # Step 1: Find explicitly mentioned files
        explicit_files = self._find_explicit_files(task_description)
        for path in explicit_files:
            if self._is_valid_file(path):
                content = self._read_file(path)
                if content:
                    result.files.append(FileContext(
                        path=path,
                        content=content,
                        relevance_score=1.0,
                        match_reason="explicit_mention",
                    ))

        # Step 2: Extract keywords from task
        keywords = self._extract_keywords(task_description)

        # Step 3: Search for files matching keywords
        if keywords:
            keyword_files = self._find_files_by_keywords(keywords)
            for path, score, keyword in keyword_files:
                # Skip if already included
                if any(f.path == path for f in result.files):
                    continue

                if len(result.files) >= self.max_files:
                    result.truncated = True
                    break

                content = self._read_file(path)
                if content:
                    result.files.append(FileContext(
                        path=path,
                        content=content,
                        relevance_score=score,
                        match_reason=f"keyword_match:{keyword}",
                    ))

        # Step 4: Find imports for explicit files (add dependencies)
        imports_to_add = []
        for fc in result.files[:3]:  # Only check top 3 files
            imports = self._find_imports(fc.path, fc.content)
            for imp_path in imports:
                if any(f.path == imp_path for f in result.files):
                    continue
                if any(p == imp_path for p, _, _ in imports_to_add):
                    continue
                imports_to_add.append((imp_path, 0.7, "import_dependency"))

        for path, score, reason in imports_to_add:
            if len(result.files) >= self.max_files:
                result.truncated = True
                break
            content = self._read_file(path)
            if content:
                result.files.append(FileContext(
                    path=path,
                    content=content,
                    relevance_score=score,
                    match_reason=reason,
                ))

        # Calculate total tokens
        for fc in result.files:
            result.total_tokens += len(fc.content) // 4

        # Truncate if over budget
        if result.total_tokens > self.max_tokens:
            result = self._apply_token_budget(result)

        return result

    def _find_explicit_files(self, text: str) -> list[Path]:
        """Find file paths explicitly mentioned in text."""
        files = []

        # Pattern 1: Unix-style paths (src/foo/bar.py)
        path_pattern = r"(?:^|[\s`\"'(])([a-zA-Z0-9_/.-]+\.[a-zA-Z0-9]+)"
        for match in re.finditer(path_pattern, text):
            path_str = match.group(1)
            # Check if it looks like a file path
            if "/" in path_str or path_str.startswith("."):
                path = self.project_dir / path_str
                if path.exists() and path.is_file():
                    files.append(path)

        # Pattern 2: Module references (ringmaster.enricher.pipeline)
        module_pattern = r"(?:^|[\s`\"'(])([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)"
        for match in re.finditer(module_pattern, text):
            module = match.group(1)
            # Convert module.path to file path
            path_str = module.replace(".", "/") + ".py"
            path = self.project_dir / "src" / path_str
            if path.exists():
                files.append(path)

        return files

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract searchable keywords from task description."""
        keywords = []

        # Extract identifiers (function/class names)
        # CamelCase, snake_case, UPPER_CASE
        identifier_pattern = r"\b([A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)*)\b"  # CamelCase
        for match in re.finditer(identifier_pattern, text):
            word = match.group(1)
            if len(word) > 2 and word not in {"The", "This", "That", "When", "TODO"}:
                keywords.append(word)

        # snake_case identifiers
        snake_pattern = r"\b([a-z][a-z0-9]*_[a-z0-9_]+)\b"
        for match in re.finditer(snake_pattern, text):
            keywords.append(match.group(1))

        # Remove duplicates, preserve order
        seen = set()
        unique = []
        for kw in keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)

        return unique[:10]  # Limit keywords

    def _find_files_by_keywords(
        self, keywords: list[str]
    ) -> list[tuple[Path, float, str]]:
        """Find files containing keywords.

        Returns list of (path, score, matched_keyword).
        """
        matches: list[tuple[Path, float, str]] = []

        for path in self._iter_code_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                logger.debug("Skipping file %s: %s: %s", path, type(e).__name__, e)
                continue

            for keyword in keywords:
                # Check for keyword in file content
                if keyword in content:
                    # Score based on number of matches
                    count = content.count(keyword)
                    score = min(0.3 + (count * 0.1), 0.9)

                    # Boost if in filename
                    if keyword.lower() in path.stem.lower():
                        score = min(score + 0.2, 0.95)

                    matches.append((path, score, keyword))
                    break  # Only match once per file

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:self.max_files]

    def _find_imports(self, file_path: Path, content: str) -> list[Path]:
        """Find imported files from a source file."""
        imports = []

        if file_path.suffix == ".py":
            imports = self._find_python_imports(content)
        elif file_path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            imports = self._find_js_imports(content)
        elif file_path.suffix == ".rs":
            imports = self._find_rust_imports(content)

        return imports

    def _find_python_imports(self, content: str) -> list[Path]:
        """Extract Python import paths."""
        paths = []

        # from X import Y
        from_pattern = r"^from\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s+import"
        for match in re.finditer(from_pattern, content, re.MULTILINE):
            module = match.group(1)
            # Only include local modules (starting with ringmaster or .)
            if module.startswith("ringmaster"):
                path_str = module.replace(".", "/") + ".py"
                path = self.project_dir / "src" / path_str
                if path.exists():
                    paths.append(path)

        return paths

    def _find_js_imports(self, content: str) -> list[Path]:
        """Extract JS/TS import paths."""
        paths = []

        # import X from 'Y'
        import_pattern = r"(?:import|from)\s+['\"]([^'\"]+)['\"]"
        for match in re.finditer(import_pattern, content):
            imp = match.group(1)
            if imp.startswith("."):
                # Relative import - would need context of file location
                pass

        return paths

    def _find_rust_imports(self, content: str) -> list[Path]:
        """Extract Rust use paths."""
        # Simplified - Rust uses are complex
        return []

    def _iter_code_files(self):
        """Iterate over code files in the project."""
        for path in self.project_dir.rglob("*"):
            if not path.is_file():
                continue

            # Skip ignored directories
            if any(part in IGNORE_PATTERNS for part in path.parts):
                continue

            # Only include code files
            if path.suffix in CODE_EXTENSIONS:
                yield path

    def _is_valid_file(self, path: Path) -> bool:
        """Check if a file should be included."""
        if not path.exists() or not path.is_file():
            return False

        if any(part in IGNORE_PATTERNS for part in path.parts):
            return False

        return path.suffix in CODE_EXTENSIONS

    def _read_file(self, path: Path) -> str | None:
        """Read a file with line limit."""
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > self.max_file_lines:
                lines = lines[: self.max_file_lines]
                lines.append(f"... (truncated, {len(lines)} more lines)")
            return "\n".join(lines)
        except OSError as e:
            logger.warning("Failed to read %s: %s", path, e)
            return None

    def _apply_token_budget(self, result: CodeContextResult) -> CodeContextResult:
        """Truncate files to fit within token budget."""
        # Sort by relevance score
        result.files.sort(key=lambda f: f.relevance_score, reverse=True)

        new_files = []
        tokens_used = 0

        for fc in result.files:
            file_tokens = len(fc.content) // 4
            if tokens_used + file_tokens <= self.max_tokens:
                new_files.append(fc)
                tokens_used += file_tokens
            else:
                result.truncated = True
                # Try to fit a truncated version
                remaining = self.max_tokens - tokens_used
                if remaining > 500:  # At least 500 tokens
                    lines = fc.content.splitlines()
                    truncated_lines = []
                    line_tokens = 0
                    for line in lines:
                        line_tokens += len(line) // 4
                        if line_tokens > remaining - 50:
                            break
                        truncated_lines.append(line)
                    if truncated_lines:
                        truncated_lines.append("... (truncated for token budget)")
                        new_files.append(FileContext(
                            path=fc.path,
                            content="\n".join(truncated_lines),
                            relevance_score=fc.relevance_score,
                            match_reason=fc.match_reason,
                        ))
                        tokens_used += len("\n".join(truncated_lines)) // 4
                break

        result.files = new_files
        result.total_tokens = tokens_used
        return result


def format_code_context(result: CodeContextResult, project_dir: Path) -> str:
    """Format code context for prompt inclusion."""
    if not result.files:
        return ""

    parts = ["## Code Context", ""]

    for fc in result.files:
        # Use relative path
        try:
            rel_path = fc.path.relative_to(project_dir)
        except ValueError:
            rel_path = fc.path

        parts.append(f"### {rel_path}")
        parts.append(f"```{fc.path.suffix.lstrip('.')}")
        parts.append(fc.content)
        parts.append("```")
        parts.append("")

    if result.truncated:
        parts.append("_(Some files omitted due to context limits)_")
        parts.append("")

    return "\n".join(parts)
