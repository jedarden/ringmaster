"""File browser API routes."""

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, ProjectRepository
from ringmaster.git import (
    GitError,
    get_file_at_commit,
    get_file_diff,
    get_file_history,
    is_git_repo,
)

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


# Git History & Diff Models


class CommitInfo(BaseModel):
    """Git commit information."""

    hash: str
    short_hash: str
    message: str
    author_name: str
    author_email: str
    date: datetime
    additions: int
    deletions: int


class FileHistoryResponse(BaseModel):
    """Response for file git history."""

    path: str
    commits: list[CommitInfo]
    is_git_repo: bool


class DiffHunkInfo(BaseModel):
    """A hunk of changes in a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: list[str]


class FileDiffResponse(BaseModel):
    """Response for file diff."""

    path: str
    old_path: str
    new_path: str
    is_new: bool
    is_deleted: bool
    is_renamed: bool
    hunks: list[DiffHunkInfo]
    additions: int
    deletions: int
    raw: str


class FileAtCommitResponse(BaseModel):
    """Response for file content at a specific commit."""

    path: str
    commit: str
    content: str | None
    exists: bool


# Git History & Diff Endpoints


@router.get("/{project_id}/files/history")
async def get_file_git_history(
    project_id: str,
    db: Annotated[Database, Depends(get_db)],
    path: str = Query(..., description="Relative path to file"),
    max_commits: int = Query(default=50, le=100, description="Maximum commits to return"),
) -> FileHistoryResponse:
    """Get the git history for a file."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_root = get_project_root(project.settings, project.repo_url)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="Project has no configured working directory.",
        )

    # Security check
    target_path = project_root / path
    if not is_safe_path(project_root, target_path):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if git repo
    is_repo = await is_git_repo(project_root)
    if not is_repo:
        return FileHistoryResponse(
            path=path,
            commits=[],
            is_git_repo=False,
        )

    try:
        commits = await get_file_history(project_root, path, max_commits)
        return FileHistoryResponse(
            path=path,
            commits=[
                CommitInfo(
                    hash=c.hash,
                    short_hash=c.short_hash,
                    message=c.message,
                    author_name=c.author_name,
                    author_email=c.author_email,
                    date=c.date,
                    additions=c.additions,
                    deletions=c.deletions,
                )
                for c in commits
            ],
            is_git_repo=True,
        )
    except GitError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{project_id}/files/diff")
async def get_file_git_diff(
    project_id: str,
    db: Annotated[Database, Depends(get_db)],
    path: str = Query(..., description="Relative path to file"),
    commit: str = Query(default="HEAD", description="Commit to show diff for"),
    against: str | None = Query(default=None, description="Commit to diff against"),
) -> FileDiffResponse:
    """Get the git diff for a file.

    If commit is HEAD and against is None, shows uncommitted changes.
    If commit is specified and against is None, shows diff against parent.
    If both are specified, shows diff between the two commits.
    """
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_root = get_project_root(project.settings, project.repo_url)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="Project has no configured working directory.",
        )

    # Security check
    target_path = project_root / path
    if not is_safe_path(project_root, target_path):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if git repo
    is_repo = await is_git_repo(project_root)
    if not is_repo:
        raise HTTPException(status_code=400, detail="Not a git repository")

    try:
        diff = await get_file_diff(project_root, path, commit, against)
        return FileDiffResponse(
            path=path,
            old_path=diff.old_path,
            new_path=diff.new_path,
            is_new=diff.is_new,
            is_deleted=diff.is_deleted,
            is_renamed=diff.is_renamed,
            hunks=[
                DiffHunkInfo(
                    old_start=h.old_start,
                    old_count=h.old_count,
                    new_start=h.new_start,
                    new_count=h.new_count,
                    header=h.header,
                    lines=h.lines,
                )
                for h in diff.hunks
            ],
            additions=diff.additions,
            deletions=diff.deletions,
            raw=diff.raw,
        )
    except GitError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{project_id}/files/at-commit")
async def get_file_content_at_commit(
    project_id: str,
    db: Annotated[Database, Depends(get_db)],
    path: str = Query(..., description="Relative path to file"),
    commit: str = Query(..., description="Commit hash or ref"),
) -> FileAtCommitResponse:
    """Get the content of a file at a specific commit."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_root = get_project_root(project.settings, project.repo_url)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="Project has no configured working directory.",
        )

    # Security check
    target_path = project_root / path
    if not is_safe_path(project_root, target_path):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if git repo
    is_repo = await is_git_repo(project_root)
    if not is_repo:
        raise HTTPException(status_code=400, detail="Not a git repository")

    try:
        content = await get_file_at_commit(project_root, path, commit)
        return FileAtCommitResponse(
            path=path,
            commit=commit,
            content=content,
            exists=content is not None,
        )
    except GitError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
