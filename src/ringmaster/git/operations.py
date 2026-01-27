"""Git operations for file history and diff viewing."""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""

    pass


@dataclass
class FileCommit:
    """A commit that modified a file."""

    hash: str
    short_hash: str
    message: str
    author_name: str
    author_email: str
    date: datetime
    # Number of lines added and removed in this commit for this file
    additions: int = 0
    deletions: int = 0


@dataclass
class DiffHunk:
    """A hunk of changes in a diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str  # The @@ line
    lines: list[str]  # The actual diff lines


@dataclass
class FileDiff:
    """Diff information for a file."""

    old_path: str
    new_path: str
    is_new: bool
    is_deleted: bool
    is_renamed: bool
    hunks: list[DiffHunk]
    additions: int
    deletions: int
    # Raw diff text for fallback rendering
    raw: str


async def _run_git_command(
    args: list[str], cwd: Path, timeout: float = 30.0
) -> tuple[str, str, int]:
    """Run a git command and return stdout, stderr, and return code."""
    cmd = ["git"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )
    except TimeoutError as err:
        raise GitError(f"Git command timed out: {' '.join(cmd)}") from err
    except Exception as err:
        raise GitError(f"Failed to run git command: {err}") from err


async def is_git_repo(path: Path) -> bool:
    """Check if the given path is inside a git repository."""
    try:
        stdout, stderr, rc = await _run_git_command(
            ["rev-parse", "--is-inside-work-tree"], path
        )
        return rc == 0 and stdout.strip() == "true"
    except GitError:
        return False


async def get_file_history(
    repo_path: Path,
    file_path: str,
    max_commits: int = 50,
) -> list[FileCommit]:
    """Get the git history for a specific file.

    Args:
        repo_path: Path to the git repository root
        file_path: Relative path to the file within the repo
        max_commits: Maximum number of commits to return

    Returns:
        List of FileCommit objects, most recent first

    Raises:
        GitError: If git command fails
    """
    # Use a custom format for easier parsing
    # Format: hash|short_hash|author_name|author_email|unix_timestamp|subject
    format_str = "%H|%h|%an|%ae|%at|%s"

    args = [
        "log",
        f"--format={format_str}",
        f"-n{max_commits}",
        "--numstat",  # Include additions/deletions
        "--follow",  # Follow file renames
        "--",
        file_path,
    ]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        if "does not have any commits" in stderr:
            return []
        raise GitError(f"Failed to get file history: {stderr}")

    commits: list[FileCommit] = []
    current_commit: FileCommit | None = None

    for line in stdout.strip().split("\n"):
        if not line:
            continue

        # Check if this is a commit line (has 6 pipe-separated fields)
        if line.count("|") >= 5:
            # Parse commit info
            parts = line.split("|", 5)
            if len(parts) == 6:
                hash_full, short_hash, author, email, timestamp, subject = parts
                current_commit = FileCommit(
                    hash=hash_full,
                    short_hash=short_hash,
                    author_name=author,
                    author_email=email,
                    date=datetime.fromtimestamp(int(timestamp), tz=UTC),
                    message=subject,
                    additions=0,
                    deletions=0,
                )
                commits.append(current_commit)
        elif current_commit and line.strip():
            # This might be a numstat line (additions\tdeletions\tfilename)
            numstat_match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if numstat_match:
                adds, dels, _ = numstat_match.groups()
                if adds != "-":
                    current_commit.additions = int(adds)
                if dels != "-":
                    current_commit.deletions = int(dels)

    return commits


async def get_file_diff(
    repo_path: Path,
    file_path: str,
    commit: str = "HEAD",
    against: str | None = None,
) -> FileDiff:
    """Get the diff for a file.

    Args:
        repo_path: Path to the git repository root
        file_path: Relative path to the file within the repo
        commit: The commit to show (default: HEAD for working tree diff)
        against: Optional commit to diff against. If None:
                 - For commit=HEAD: diffs working tree against HEAD
                 - For other commits: diffs against parent commit

    Returns:
        FileDiff object with the diff information

    Raises:
        GitError: If git command fails
    """
    if against:
        # Explicit diff between two commits
        args = ["diff", against, commit, "--", file_path]
    elif commit == "HEAD":
        # Diff working tree against HEAD (uncommitted changes)
        args = ["diff", "HEAD", "--", file_path]
    else:
        # Diff this commit against its parent
        args = ["diff", f"{commit}^", commit, "--", file_path]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0 and stderr:
        # Check for common errors
        if "unknown revision" in stderr:
            raise GitError(f"Unknown commit: {commit}")
        raise GitError(f"Failed to get diff: {stderr}")

    return _parse_diff(stdout, file_path)


def _parse_diff(diff_output: str, file_path: str) -> FileDiff:
    """Parse git diff output into a FileDiff object."""
    hunks: list[DiffHunk] = []
    additions = 0
    deletions = 0
    old_path = file_path
    new_path = file_path
    is_new = False
    is_deleted = False
    is_renamed = False

    lines = diff_output.split("\n")
    i = 0

    # Parse diff header
    while i < len(lines):
        line = lines[i]

        if line.startswith("--- "):
            # Old file path
            if line == "--- /dev/null":
                is_new = True
            else:
                # Strip "a/" prefix
                old_path = line[4:].lstrip("a/")
        elif line.startswith("+++ "):
            # New file path
            if line == "+++ /dev/null":
                is_deleted = True
            else:
                # Strip "b/" prefix
                new_path = line[4:].lstrip("b/")
        elif line.startswith("rename from "):
            is_renamed = True
            old_path = line[12:]
        elif line.startswith("rename to "):
            new_path = line[10:]
        elif line.startswith("@@"):
            # Start of a hunk - parse it
            hunk = _parse_hunk(lines, i)
            if hunk:
                hunks.append(hunk)
                # Count additions and deletions
                for hunk_line in hunk.lines:
                    if hunk_line.startswith("+") and not hunk_line.startswith("+++"):
                        additions += 1
                    elif hunk_line.startswith("-") and not hunk_line.startswith("---"):
                        deletions += 1
                # Skip past this hunk
                i += len(hunk.lines) + 1
                continue

        i += 1

    return FileDiff(
        old_path=old_path,
        new_path=new_path,
        is_new=is_new,
        is_deleted=is_deleted,
        is_renamed=is_renamed,
        hunks=hunks,
        additions=additions,
        deletions=deletions,
        raw=diff_output,
    )


def _parse_hunk(lines: list[str], start: int) -> DiffHunk | None:
    """Parse a single diff hunk starting at the given line index."""
    if start >= len(lines):
        return None

    header_line = lines[start]

    # Parse @@ -old_start,old_count +new_start,new_count @@ optional context
    match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$", header_line)
    if not match:
        return None

    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) else 1

    # Collect hunk lines
    hunk_lines: list[str] = []
    i = start + 1

    while i < len(lines):
        line = lines[i]
        # A hunk line starts with +, -, space, or \ (no newline marker)
        if line.startswith(("+", "-", " ", "\\")) or line == "":
            # Stop if we hit a new hunk header or diff header
            if line.startswith("@@") or line.startswith("diff --git"):
                break
            hunk_lines.append(line)
            i += 1
        else:
            # End of hunk
            break

    return DiffHunk(
        old_start=old_start,
        old_count=old_count,
        new_start=new_start,
        new_count=new_count,
        header=header_line,
        lines=hunk_lines,
    )


async def get_file_at_commit(
    repo_path: Path,
    file_path: str,
    commit: str,
) -> str | None:
    """Get the content of a file at a specific commit.

    Args:
        repo_path: Path to the git repository root
        file_path: Relative path to the file within the repo
        commit: The commit hash or ref

    Returns:
        File content as string, or None if file didn't exist at that commit

    Raises:
        GitError: If git command fails
    """
    args = ["show", f"{commit}:{file_path}"]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        if "does not exist" in stderr or "path" in stderr.lower():
            return None
        raise GitError(f"Failed to get file at commit: {stderr}")

    return stdout
