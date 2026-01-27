"""Tests for git operations and API endpoints."""

import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ringmaster.api.app import create_app
from ringmaster.db.connection import Database
from ringmaster.domain import Project
from ringmaster.git import (
    get_file_diff,
    get_file_history,
    get_file_at_commit,
    is_git_repo,
)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with some commits."""
    import subprocess

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial file and commit
    test_file = repo_path / "test.py"
    test_file.write_text("# Initial content\nprint('hello')\n")
    subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Second commit - modify the file
    test_file.write_text("# Initial content\nprint('hello')\nprint('world')\n")
    subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add print world"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Third commit - add a new file
    new_file = repo_path / "new_file.py"
    new_file.write_text("# New file\n")
    subprocess.run(["git", "add", "new_file.py"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add new file"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


class TestGitOperations:
    """Tests for git helper functions."""

    async def test_is_git_repo_true(self, temp_git_repo: Path):
        """Test is_git_repo returns True for git repository."""
        result = await is_git_repo(temp_git_repo)
        assert result is True

    async def test_is_git_repo_false(self, tmp_path: Path):
        """Test is_git_repo returns False for non-git directory."""
        result = await is_git_repo(tmp_path)
        assert result is False

    async def test_get_file_history(self, temp_git_repo: Path):
        """Test getting file history."""
        commits = await get_file_history(temp_git_repo, "test.py")

        # Should have 2 commits for test.py
        assert len(commits) == 2
        # Most recent first
        assert commits[0].message == "Add print world"
        assert commits[1].message == "Initial commit"

        # Check commit properties
        assert commits[0].short_hash is not None
        assert len(commits[0].hash) == 40
        # Author name comes from git config which may vary by environment
        assert commits[0].author_name is not None
        assert len(commits[0].author_name) > 0

    async def test_get_file_history_with_stats(self, temp_git_repo: Path):
        """Test that file history includes addition/deletion counts."""
        commits = await get_file_history(temp_git_repo, "test.py")

        # The second commit added one line
        assert commits[0].additions == 1
        assert commits[0].deletions == 0

    async def test_get_file_history_max_commits(self, temp_git_repo: Path):
        """Test limiting the number of commits returned."""
        commits = await get_file_history(temp_git_repo, "test.py", max_commits=1)
        assert len(commits) == 1
        assert commits[0].message == "Add print world"

    async def test_get_file_history_nonexistent_file(self, temp_git_repo: Path):
        """Test getting history for a file that never existed."""
        commits = await get_file_history(temp_git_repo, "nonexistent.py")
        assert commits == []

    async def test_get_file_diff_against_parent(self, temp_git_repo: Path):
        """Test getting diff of a commit against its parent."""
        # Get the most recent commit hash
        commits = await get_file_history(temp_git_repo, "test.py")
        commit_hash = commits[0].hash

        diff = await get_file_diff(temp_git_repo, "test.py", commit=commit_hash)

        assert diff.additions == 1
        assert diff.deletions == 0
        assert len(diff.hunks) == 1
        # Check that the added line is in the diff
        assert any("print('world')" in line for line in diff.hunks[0].lines)

    async def test_get_file_diff_working_tree(self, temp_git_repo: Path):
        """Test getting diff for uncommitted changes."""
        # Modify the file without committing
        test_file = temp_git_repo / "test.py"
        test_file.write_text("# Modified\nprint('hello')\nprint('world')\nprint('foo')\n")

        diff = await get_file_diff(temp_git_repo, "test.py", commit="HEAD")

        # Should show the uncommitted changes
        assert diff.additions > 0
        assert any("print('foo')" in line for line in diff.hunks[0].lines) if diff.hunks else False

    async def test_get_file_at_commit(self, temp_git_repo: Path):
        """Test getting file content at a specific commit."""
        commits = await get_file_history(temp_git_repo, "test.py")

        # Get content at initial commit (second in list since most recent first)
        initial_hash = commits[1].hash
        content = await get_file_at_commit(temp_git_repo, "test.py", initial_hash)

        assert content is not None
        assert "print('hello')" in content
        assert "print('world')" not in content  # Not yet added

    async def test_get_file_at_commit_not_exists(self, temp_git_repo: Path):
        """Test getting file that didn't exist at that commit."""
        commits = await get_file_history(temp_git_repo, "test.py")
        initial_hash = commits[1].hash  # Initial commit

        # new_file.py was added in a later commit
        content = await get_file_at_commit(temp_git_repo, "new_file.py", initial_hash)
        assert content is None


@pytest.fixture
async def app_with_git_project() -> AsyncGenerator[tuple, None]:
    """Create an app with a temporary database and git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        db_path = tmpdir_path / "test.db"
        repo_path = tmpdir_path / "test_repo"

        # Create git repo
        import subprocess

        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create a file and commit
        test_file = repo_path / "main.py"
        test_file.write_text("# Main file\nprint('hello')\n")
        subprocess.run(["git", "add", "main.py"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Connect to database
        db = Database(db_path)
        await db.connect()

        # Create app
        app = create_app()
        app.state.db = db

        yield app, db, repo_path

        await db.disconnect()


@pytest.fixture
async def client_with_git(app_with_git_project) -> AsyncGenerator[tuple, None]:
    """Create a test client with git project."""
    app, db, repo_path = app_with_git_project
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db, repo_path


class TestGitAPI:
    """Tests for git API endpoints."""

    async def test_file_history_endpoint(self, client_with_git):
        """Test GET /api/{project_id}/files/history endpoint."""
        client, db, repo_path = client_with_git

        # Create a project pointing to the git repo
        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Test Project",
            description="Project for git testing",
            settings={"working_dir": str(repo_path)},
        )
        project = await project_repo.create(project)

        response = await client.get(
            f"/api/projects/{project.id}/files/history",
            params={"path": "main.py"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "main.py"
        assert data["is_git_repo"] is True
        assert len(data["commits"]) == 1
        assert data["commits"][0]["message"] == "Initial commit"
        # Author can vary by environment
        assert data["commits"][0]["author_name"] is not None

    async def test_file_history_not_git_repo(self, client_with_git, tmp_path: Path):
        """Test file history for non-git project."""
        client, db, _ = client_with_git

        # Create a project pointing to non-git directory
        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Non-Git Project",
            settings={"working_dir": str(tmp_path)},
        )
        project = await project_repo.create(project)

        # Create a file in the directory
        (tmp_path / "test.txt").write_text("test")

        response = await client.get(
            f"/api/projects/{project.id}/files/history",
            params={"path": "test.txt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_git_repo"] is False
        assert data["commits"] == []

    async def test_file_diff_endpoint(self, client_with_git):
        """Test GET /api/{project_id}/files/diff endpoint."""
        client, db, repo_path = client_with_git

        # Create a project
        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Test Project",
            settings={"working_dir": str(repo_path)},
        )
        project = await project_repo.create(project)

        # Modify the file to create uncommitted changes
        (repo_path / "main.py").write_text("# Main file\nprint('hello')\nprint('new line')\n")

        response = await client.get(
            f"/api/projects/{project.id}/files/diff",
            params={"path": "main.py"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "main.py"
        assert data["additions"] > 0
        assert len(data["hunks"]) > 0

    async def test_file_diff_not_git_repo(self, client_with_git, tmp_path: Path):
        """Test diff endpoint for non-git project returns error."""
        client, db, _ = client_with_git

        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Non-Git Project",
            settings={"working_dir": str(tmp_path)},
        )
        project = await project_repo.create(project)

        (tmp_path / "test.txt").write_text("test")

        response = await client.get(
            f"/api/projects/{project.id}/files/diff",
            params={"path": "test.txt"},
        )

        assert response.status_code == 400
        assert "Not a git repository" in response.json()["detail"]

    async def test_file_at_commit_endpoint(self, client_with_git):
        """Test GET /api/{project_id}/files/at-commit endpoint."""
        client, db, repo_path = client_with_git

        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Test Project",
            settings={"working_dir": str(repo_path)},
        )
        project = await project_repo.create(project)

        # Get the commit hash
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_hash = result.stdout.strip()

        response = await client.get(
            f"/api/projects/{project.id}/files/at-commit",
            params={"path": "main.py", "commit": commit_hash},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "main.py"
        assert data["commit"] == commit_hash
        assert data["exists"] is True
        assert "print('hello')" in data["content"]

    async def test_file_at_commit_nonexistent_file(self, client_with_git):
        """Test at-commit endpoint for file that doesn't exist."""
        client, db, repo_path = client_with_git

        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Test Project",
            settings={"working_dir": str(repo_path)},
        )
        project = await project_repo.create(project)

        response = await client.get(
            f"/api/projects/{project.id}/files/at-commit",
            params={"path": "nonexistent.py", "commit": "HEAD"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["content"] is None

    async def test_file_history_path_traversal(self, client_with_git):
        """Test that path traversal is blocked."""
        client, db, repo_path = client_with_git

        from ringmaster.db import ProjectRepository

        project_repo = ProjectRepository(db)
        project = Project(
            name="Test Project",
            settings={"working_dir": str(repo_path)},
        )
        project = await project_repo.create(project)

        response = await client.get(
            f"/api/projects/{project.id}/files/history",
            params={"path": "../../../etc/passwd"},
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]
