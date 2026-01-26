"""File browser API routes."""

import mimetypes
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, ProjectRepository

router = APIRouter()


class FileEntry(BaseModel):
    """A file or directory entry."""

    name: str
    path: str  # Relative path from project root
    is_dir: bool
    size: int | None = None  # None for directories
    modified_at: float | None = None  # Unix timestamp


class DirectoryListing(BaseModel):
    """Response for directory listing."""

    path: str  # Current path relative to project root
    entries: list[FileEntry]
    parent_path: str | None  # None if at root


class FileContent(BaseModel):
    """Response for file content."""

    path: str
    content: str
    size: int
    mime_type: str | None
    is_binary: bool


# File extensions we consider safe to read as text
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".md", ".txt", ".rst", ".html", ".css", ".scss", ".sass", ".less",
    ".xml", ".svg", ".sh", ".bash", ".zsh", ".fish",
    ".toml", ".ini", ".cfg", ".conf", ".env", ".env.example",
    ".gitignore", ".dockerignore", ".editorconfig",
    ".sql", ".graphql", ".prisma",
    ".go", ".rs", ".rb", ".php", ".java", ".kt", ".kts", ".scala",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".m", ".mm",
    ".vue", ".svelte", ".astro",
    ".lock", ".sum",  # Lock files
    "Dockerfile", "Makefile", "CMakeLists.txt",
}

# Directories to ignore
IGNORED_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".pytest_cache",
    ".venv", "venv", "env", ".env",
    ".mypy_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt",
    "target",  # Rust/Java
    ".idea", ".vscode",
}

# Maximum file size to read (1MB)
MAX_FILE_SIZE = 1024 * 1024


def get_project_root(project_settings: dict, repo_url: str | None) -> Path | None:
    """Get the project root directory from settings or repo_url."""
    # First check settings for explicit working_dir
    if "working_dir" in project_settings:
        path = Path(project_settings["working_dir"])
        if path.exists() and path.is_dir():
            return path

    # If repo_url is a local path, use it
    if repo_url and not repo_url.startswith(("http://", "https://", "git@")):
        path = Path(repo_url)
        if path.exists() and path.is_dir():
            return path

    return None


def is_safe_path(project_root: Path, requested_path: Path) -> bool:
    """Check if the requested path is within the project root (prevent traversal)."""
    try:
        resolved = requested_path.resolve()
        root = project_root.resolve()
        return str(resolved).startswith(str(root))
    except (ValueError, RuntimeError):
        return False


def is_text_file(path: Path) -> bool:
    """Determine if a file is likely a text file."""
    # Check extension
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True

    # Check filename (no extension)
    if path.name in TEXT_EXTENSIONS:
        return True

    # Check mime type
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("text/"))


@router.get("/{project_id}/files")
async def list_directory(
    project_id: str,
    db: Annotated[Database, Depends(get_db)],
    path: str = Query(default="", description="Relative path within project"),
) -> DirectoryListing:
    """List files and directories in a project."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_root = get_project_root(project.settings, project.repo_url)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="Project has no configured working directory. Set repo_url or settings.working_dir.",
        )

    # Resolve the requested path
    target_path = project_root / path if path else project_root

    # Security check
    if not is_safe_path(project_root, target_path):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    # List entries
    entries: list[FileEntry] = []
    try:
        for entry in sorted(target_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            # Skip ignored directories
            if entry.is_dir() and entry.name in IGNORED_DIRS:
                continue

            # Skip hidden files (optional, but common)
            if entry.name.startswith(".") and entry.name not in {".env.example", ".gitignore", ".dockerignore", ".editorconfig"}:
                continue

            try:
                stat = entry.stat()
                entries.append(
                    FileEntry(
                        name=entry.name,
                        path=str(entry.relative_to(project_root)),
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else None,
                        modified_at=stat.st_mtime,
                    )
                )
            except (PermissionError, OSError):
                # Skip files we can't access
                continue
    except PermissionError as err:
        raise HTTPException(status_code=403, detail="Permission denied") from err

    # Calculate parent path
    parent_path = None
    if path:
        parent = Path(path).parent
        parent_path = "" if parent == Path(".") else str(parent)

    return DirectoryListing(
        path=path or "",
        entries=entries,
        parent_path=parent_path,
    )


@router.get("/{project_id}/files/content")
async def get_file_content(
    project_id: str,
    db: Annotated[Database, Depends(get_db)],
    path: str = Query(..., description="Relative path to file"),
) -> FileContent:
    """Get the content of a file."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_root = get_project_root(project.settings, project.repo_url)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="Project has no configured working directory. Set repo_url or settings.working_dir.",
        )

    target_path = project_root / path

    # Security check
    if not is_safe_path(project_root, target_path):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Check file size
    stat = target_path.stat()
    if stat.st_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({stat.st_size} bytes). Maximum is {MAX_FILE_SIZE} bytes.",
        )

    # Determine if binary
    is_text = is_text_file(target_path)
    mime_type, _ = mimetypes.guess_type(str(target_path))

    if not is_text:
        return FileContent(
            path=path,
            content="[Binary file - preview not available]",
            size=stat.st_size,
            mime_type=mime_type,
            is_binary=True,
        )

    # Read content
    try:
        content = target_path.read_text(encoding="utf-8", errors="replace")
    except (PermissionError, OSError) as e:
        raise HTTPException(status_code=403, detail=f"Cannot read file: {e}") from e

    return FileContent(
        path=path,
        content=content,
        size=stat.st_size,
        mime_type=mime_type,
        is_binary=False,
    )
