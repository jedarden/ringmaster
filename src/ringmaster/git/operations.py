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


@dataclass
class RevertResult:
    """Result of a git revert operation."""

    success: bool
    new_commit_hash: str | None  # The hash of the revert commit, if created
    message: str
    conflicts: list[str] | None = None  # Files with conflicts, if any


async def get_commit_info(repo_path: Path, commit: str) -> FileCommit:
    """Get information about a specific commit.

    Args:
        repo_path: Path to the git repository root
        commit: The commit hash or ref

    Returns:
        FileCommit object with commit information

    Raises:
        GitError: If commit doesn't exist or git command fails
    """
    format_str = "%H|%h|%an|%ae|%at|%s"
    args = ["show", f"--format={format_str}", "-s", commit]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        if "unknown revision" in stderr or "bad object" in stderr:
            raise GitError(f"Commit not found: {commit}")
        raise GitError(f"Failed to get commit info: {stderr}")

    line = stdout.strip()
    parts = line.split("|", 5)
    if len(parts) != 6:
        raise GitError(f"Failed to parse commit info: {line}")

    hash_full, short_hash, author, email, timestamp, subject = parts
    return FileCommit(
        hash=hash_full,
        short_hash=short_hash,
        author_name=author,
        author_email=email,
        date=datetime.fromtimestamp(int(timestamp), tz=UTC),
        message=subject,
        additions=0,
        deletions=0,
    )


async def revert_commit(
    repo_path: Path,
    commit: str,
    no_commit: bool = False,
) -> RevertResult:
    """Revert a single commit.

    Creates a new commit that undoes the changes from the specified commit.

    Args:
        repo_path: Path to the git repository root
        commit: The commit hash to revert
        no_commit: If True, stages the revert changes without committing

    Returns:
        RevertResult with operation outcome

    Raises:
        GitError: If git command fails (other than merge conflicts)
    """
    args = ["revert", "--no-edit", commit]
    if no_commit:
        args.insert(1, "--no-commit")

    stdout, stderr, rc = await _run_git_command(args, repo_path, timeout=60.0)

    if rc == 0:
        # Success - get the new commit hash if committed
        if no_commit:
            return RevertResult(
                success=True,
                new_commit_hash=None,
                message="Revert changes staged (not committed)",
            )
        else:
            # Get the hash of the revert commit
            hash_out, _, _ = await _run_git_command(
                ["rev-parse", "HEAD"], repo_path
            )
            return RevertResult(
                success=True,
                new_commit_hash=hash_out.strip(),
                message=f"Successfully reverted commit {commit[:8]}",
            )

    # Check for merge conflicts
    if "CONFLICT" in stderr or "conflict" in stderr.lower():
        # Extract conflicted files
        conflicts = _extract_conflicts(stderr)
        return RevertResult(
            success=False,
            new_commit_hash=None,
            message="Revert resulted in merge conflicts",
            conflicts=conflicts,
        )

    # Other error
    raise GitError(f"Failed to revert commit: {stderr}")


async def revert_to_commit(
    repo_path: Path,
    target_commit: str,
    no_commit: bool = False,
) -> RevertResult:
    """Revert all commits from HEAD back to (but not including) the target commit.

    This is equivalent to reverting each commit from HEAD to target in order.

    Args:
        repo_path: Path to the git repository root
        target_commit: The commit to revert back to (this commit will NOT be reverted)
        no_commit: If True, stages all changes without creating revert commits

    Returns:
        RevertResult with operation outcome

    Raises:
        GitError: If git command fails
    """
    # Get list of commits to revert (from HEAD to target, exclusive)
    args = ["rev-list", f"{target_commit}..HEAD"]
    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        raise GitError(f"Failed to get commit list: {stderr}")

    commits_to_revert = [c for c in stdout.strip().split("\n") if c]

    if not commits_to_revert:
        return RevertResult(
            success=True,
            new_commit_hash=None,
            message="Nothing to revert - target commit is at or ahead of HEAD",
        )

    # Revert each commit in order (oldest first would cause issues,
    # we revert newest first which is what git rev-list gives us)
    all_conflicts: list[str] = []

    for commit in commits_to_revert:
        result = await revert_commit(repo_path, commit, no_commit=no_commit)
        if not result.success:
            # Abort the revert on conflict
            await _run_git_command(["revert", "--abort"], repo_path)
            all_conflicts.extend(result.conflicts or [])
            return RevertResult(
                success=False,
                new_commit_hash=None,
                message=f"Revert stopped at {commit[:8]} due to conflicts",
                conflicts=all_conflicts,
            )

    # All reverts succeeded
    if no_commit:
        return RevertResult(
            success=True,
            new_commit_hash=None,
            message=f"Staged revert of {len(commits_to_revert)} commits",
        )
    else:
        hash_out, _, _ = await _run_git_command(["rev-parse", "HEAD"], repo_path)
        return RevertResult(
            success=True,
            new_commit_hash=hash_out.strip(),
            message=f"Reverted {len(commits_to_revert)} commits back to {target_commit[:8]}",
        )


async def revert_file_in_commit(
    repo_path: Path,
    commit: str,
    file_path: str,
) -> RevertResult:
    """Revert changes to a specific file from a commit.

    This uses `git checkout` to restore the file to its state before the commit,
    then stages the change. Does NOT create a commit.

    Args:
        repo_path: Path to the git repository root
        commit: The commit whose changes to this file should be reverted
        file_path: Relative path to the file within the repo

    Returns:
        RevertResult with operation outcome

    Raises:
        GitError: If git command fails
    """
    # Check if the file was modified in this commit
    args = ["diff-tree", "--no-commit-id", "--name-only", "-r", commit]
    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        raise GitError(f"Failed to get commit file list: {stderr}")

    files_in_commit = [f.strip() for f in stdout.strip().split("\n") if f.strip()]

    if file_path not in files_in_commit:
        return RevertResult(
            success=False,
            new_commit_hash=None,
            message=f"File '{file_path}' was not modified in commit {commit[:8]}",
        )

    # Get the parent commit
    parent_out, parent_err, parent_rc = await _run_git_command(
        ["rev-parse", f"{commit}^"], repo_path
    )

    if parent_rc != 0:
        # This might be the initial commit
        if "unknown revision" in parent_err:
            # For initial commit, we need to delete the file
            args = ["rm", "--cached", file_path]
        else:
            raise GitError(f"Failed to get parent commit: {parent_err}")
    else:
        # Restore file from parent commit
        parent_commit = parent_out.strip()
        args = ["checkout", parent_commit, "--", file_path]

    stdout, stderr, rc = await _run_git_command(args, repo_path)

    if rc != 0:
        raise GitError(f"Failed to revert file: {stderr}")

    # Stage the change
    stage_args = ["add", file_path]
    _, stage_err, stage_rc = await _run_git_command(stage_args, repo_path)

    if stage_rc != 0:
        raise GitError(f"Failed to stage reverted file: {stage_err}")

    return RevertResult(
        success=True,
        new_commit_hash=None,
        message=f"Reverted '{file_path}' to state before {commit[:8]} (staged)",
    )


async def abort_revert(repo_path: Path) -> RevertResult:
    """Abort an in-progress revert operation.

    Args:
        repo_path: Path to the git repository root

    Returns:
        RevertResult with operation outcome
    """
    _, stderr, rc = await _run_git_command(["revert", "--abort"], repo_path)

    if rc == 0:
        return RevertResult(
            success=True,
            new_commit_hash=None,
            message="Revert aborted",
        )
    # Check for various ways git says "no revert in progress"
    stderr_lower = stderr.lower()
    if (
        "no revert in progress" in stderr_lower
        or "no cherry-pick or revert in progress" in stderr_lower
    ):
        return RevertResult(
            success=True,
            new_commit_hash=None,
            message="No revert in progress",
        )
    else:
        raise GitError(f"Failed to abort revert: {stderr}")


def _extract_conflicts(stderr: str) -> list[str]:
    """Extract list of conflicted files from git stderr output."""
    conflicts: list[str] = []
    for line in stderr.split("\n"):
        # Common patterns: "CONFLICT (content): Merge conflict in <file>"
        if "CONFLICT" in line and " in " in line:
            # Extract filename after " in "
            match = re.search(r" in (.+)$", line)
            if match:
                conflicts.append(match.group(1).strip())
        # Also look for "Auto-merging <file>" followed by conflict
        elif "Auto-merging" in line:
            match = re.search(r"Auto-merging (.+)$", line)
            if match:
                potential_conflict = match.group(1).strip()
                # Only add if there's actually a conflict mentioned
                if potential_conflict not in conflicts and "CONFLICT" in stderr:
                    conflicts.append(potential_conflict)
    return list(set(conflicts))  # Deduplicate
