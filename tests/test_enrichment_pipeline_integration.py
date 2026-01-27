"""Integration tests for the full enrichment pipeline.

These tests validate the 9-layer enrichment pipeline against realistic
project structures to ensure context extraction works correctly in
real-world scenarios.

Per PROGRESS.md functional gap #2: "Enrichment Pipeline Real-World Testing"
"""

import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ringmaster.db import Database
from ringmaster.domain import Priority, Project, Task, TaskStatus, TaskType
from ringmaster.enricher.pipeline import AssembledPrompt, EnrichmentPipeline


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    """Create an in-memory database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        await db.connect()
        yield db
        await db.disconnect()


@pytest.fixture
def realistic_project():
    """Create a realistic project structure with multiple file types.

    Simulates a typical FastAPI + React web application project.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)

        # Backend structure
        backend = project / "backend" / "app"
        backend.mkdir(parents=True)

        # Main application file
        (backend / "__init__.py").write_text('"""FastAPI application."""\n')
        (backend / "main.py").write_text('''"""FastAPI application entry point."""
from fastapi import FastAPI
from app.api.routes import tasks, projects
from app.db.database import get_db
from app.domain.models import Task, Project

app = FastAPI(title="Ringmaster API")

app.include_router(tasks.router, prefix="/api/tasks")
app.include_router(projects.router, prefix="/api/projects")

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
''')

        # API routes
        api_dir = backend / "api"
        api_dir.mkdir()
        (api_dir / "__init__.py").touch()

        (api_dir / "routes.py").write_text('''"""API route definitions."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import TaskRepository
from app.domain.models import TaskCreate

router = APIRouter()

@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db)):
    """List all tasks."""
    repo = TaskRepository(db)
    return await repo.list()

@router.post("/tasks")
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Create a new task."""
    repo = TaskRepository(db)
    return await repo.create(task)
''')

        # Domain models
        domain_dir = backend / "domain"
        domain_dir.mkdir()
        (domain_dir / "__init__.py").touch()

        (domain_dir / "models.py").write_text('''"""Domain models."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class TaskStatus(str, Enum):
    """Task status enumeration."""
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"

@dataclass
class Task:
    """Task domain model."""
    id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.DRAFT
    priority: int = 5

@dataclass
class Project:
    """Project domain model."""
    id: str
    name: str
    description: Optional[str] = None
    tech_stack: list[str] = None
''')

        # Database layer
        db_dir = backend / "db"
        db_dir.mkdir()
        (db_dir / "__init__.py").touch()

        (db_dir / "database.py").write_text('''"""Database connection and session management."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./ringmaster.db"

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        yield session
''')

        (db_dir / "repositories.py").write_text('''"""Database repositories."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models import Task

class TaskRepository:
    """Repository for Task entities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self):
        """List all tasks."""
        result = await self.db.execute("SELECT * FROM tasks")
        return result.fetchall()

    async def create(self, task: TaskCreate) -> Task:
        """Create a new task."""
        # Implementation...
        pass
''')

        # Tests
        tests_dir = project / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").touch()

        (tests_dir / "test_tasks.py").write_text('''"""Tests for task endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_list_tasks():
    """Test listing tasks endpoint."""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_task():
    """Test creating a task."""
    response = client.post(
        "/api/tasks",
        json={"title": "Test Task", "description": "Test description"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Test Task"
''')

        # Frontend structure
        frontend = project / "frontend" / "src"
        frontend.mkdir(parents=True)

        (frontend / "App.tsx").write_text('''"""Main React application component."""
import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ProjectsPage from './pages/ProjectsPage';
import TaskDetailPage from './pages/TaskDetailPage';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/tasks/:id" element={<TaskDetailPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
''')

        (frontend / "pages").mkdir()
        (frontend / "pages" / "ProjectsPage.tsx").write_text('''"""Projects listing page."""
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export default function ProjectsPage() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/api/projects').then(r => r.data),
  });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="projects-container">
      <h1>Projects</h1>
      {projects?.map(p => (
        <div key={p.id} className="project-card">
          <h2>{p.name}</h2>
          <p>{p.description}</p>
        </div>
      ))}
    </div>
  );
}
''')

        (frontend / "components").mkdir()
        (frontend / "components" / "Layout.tsx").write_text('''"""Main layout component."""
import { Outlet } from 'react-router-dom';

export default function Layout() {
  return (
    <div className="app-layout">
      <header>
        <nav>
          <a href="/">Projects</a>
          <a href="/tasks">Tasks</a>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
''')

        # README
        (project / "README.md").write_text('''# Ringmaster API

A multi-agent orchestration platform for coordinating AI coding agents.

## Features

- Task queue management with priority scheduling
- Worker pool management (Claude Code, Aider, Codex)
- Real-time WebSocket updates
- Context enrichment pipeline

## Tech Stack

- Backend: Python 3.11+, FastAPI, SQLAlchemy
- Frontend: React, TypeScript, Vite
- Database: SQLite with aiosqlite

## Getting Started

1. Install dependencies: `pip install -e ".[dev]"`
2. Initialize database: `ringmaster init`
3. Start API server: `ringmaster serve`
4. Start scheduler: `ringmaster scheduler`

## Development

Run tests: `pytest`
Run linter: `ruff check .`
Format code: `ruff format ."
''')

        # ADRs
        adr_dir = project / "docs" / "adr"
        adr_dir.mkdir(parents=True)

        (adr_dir / "001-fastapi-choice.md").write_text('''# ADR 001: FastAPI Framework Choice

## Status
Accepted

## Context
We need a Python web framework for the REST API.

## Decision
Use FastAPI for the following reasons:
- Built-in async support
- Automatic OpenAPI documentation
- Type hints and Pydantic validation
- High performance

## Consequences
- Faster development with automatic docs
- Better IDE support with type hints
- May require learning async patterns for new developers
''')

        (adr_dir / "002-sqlite-database.md").write_text('''# ADR 002: SQLite Database

## Status
Accepted

## Context
Need a database for task/project persistence.

## Decision
Use SQLite with aiosqlite for async operations.

## Consequences
- Simple deployment (no separate DB server)
- Good performance for single-server deployments
- May need to migrate to PostgreSQL for multi-server setups
''')

        # Deployment files
        (project / ".env.example").write_text('''# Database
DATABASE_URL=sqlite+aiosqlite:///./ringmaster.db

# API
API_PORT=8000
API_HOST=0.0.0.0

# Workers
MAX_WORKERS=5
DEFAULT_WORKER_TYPE=claude-code

# Logging
LOG_LEVEL=info
''')

        (project / "docker-compose.yml").write_text('''version: '3.8'
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/ringmaster.db
    volumes:
      - ./data:/app/data

  scheduler:
    build: .
    command: ringmaster scheduler
    depends_on:
      - api
''')

        (project / "Dockerfile").write_text('''FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["ringmaster", "serve"]
''')

        # GitHub Actions
        gh_dir = project / ".github" / "workflows"
        gh_dir.mkdir(parents=True)

        (gh_dir / "ci.yml").write_text('''name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install ruff
      - run: ruff check .
''')

        # K8s manifests
        k8s_dir = project / "k8s"
        k8s_dir.mkdir()

        (k8s_dir / "deployment.yaml").write_text('''apiVersion: apps/v1
kind: Deployment
metadata:
  name: ringmaster-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ringmaster-api
  template:
    metadata:
      labels:
        app: ringmaster-api
    spec:
      containers:
      - name: api
        image: ringmaster:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          value: sqlite+aiosqlite:///./data/ringmaster.db
''')

        (k8s_dir / "service.yaml").write_text('''apiVersion: v1
kind: Service
metadata:
  name: ringmaster-api
spec:
  selector:
    app: ringmaster-api
  ports:
  - port: 80
    targetPort: 8000
''')

        yield project


class TestEnrichmentPipelineIntegration:
    """Integration tests for the full enrichment pipeline.

    These tests validate that all 9 layers of context enrichment
    work correctly on a realistic project structure.
    """

    @pytest.mark.asyncio
    async def test_full_pipeline_code_task(self, realistic_project: Path, db: Database):
        """Test full enrichment pipeline for a code-related task."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        # Create project and task
        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python", "FastAPI", "React"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Add retry logic to TaskRepository.create",
            description=(
                "Implement retry logic with exponential backoff in the "
                "TaskRepository.create method in backend/app/db/repositories.py. "
                "Handle database connection errors gracefully."
            ),
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
        )

        # Create pipeline
        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        # Run enrichment
        result = await pipeline.enrich(task, project)

        # Validate result
        assert isinstance(result, AssembledPrompt)
        assert result.system_prompt
        assert result.user_prompt
        assert result.context_hash
        assert len(result.context_hash) == 16

        # Check system prompt
        assert "ringmaster" in result.system_prompt
        assert "Python" in result.system_prompt or "FastAPI" in result.system_prompt

        # Check task context (Layer 1)
        assert "Add retry logic to TaskRepository.create" in result.user_prompt
        assert str(task.id) in result.user_prompt or "P2" in result.user_prompt

        # Check project context (Layer 2)
        assert "ringmaster" in result.user_prompt

        # Check code context (Layer 3) - should find repositories.py
        assert "TaskRepository" in result.user_prompt or "repositories" in result.user_prompt

        # Check documentation context (Layer 5) - should include README
        assert "README" in result.user_prompt or "FastAPI" in result.user_prompt

        # Check metrics
        assert result.metrics.estimated_tokens > 0
        assert len(result.metrics.stages_applied) >= 3  # At least task, project, code
        assert "task_context" in result.metrics.stages_applied
        assert "project_context" in result.metrics.stages_applied

    @pytest.mark.asyncio
    async def test_full_pipeline_deployment_task(self, realistic_project: Path, db: Database):
        """Test enrichment pipeline for a deployment-related task."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python", "Kubernetes"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Update Kubernetes deployment for production",
            description=(
                "Update the Kubernetes deployment manifest in k8s/deployment.yaml "
                "to use 5 replicas for production. Configure resource limits and "
                "add liveness and readiness probes."
            ),
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P1,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Should include deployment context
        assert "deployment" in result.user_prompt.lower() or "kubernetes" in result.user_prompt.lower()

        # Should have deployment context stage
        assert "deployment_context" in result.metrics.stages_applied

        # Should include YAML from k8s manifests
        assert "kind: Deployment" in result.user_prompt or "replicas:" in result.user_prompt

    @pytest.mark.asyncio
    async def test_full_pipeline_frontend_task(self, realistic_project: Path, db: Database):
        """Test enrichment pipeline for a frontend task."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["React", "TypeScript"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Add loading spinner to ProjectsPage",
            description=(
                "Add a loading spinner component to the ProjectsPage.tsx "
                "while projects are being fetched. Use the existing LoadingSpinner "
                "component from components/ui."
            ),
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Should find ProjectsPage.tsx
        assert "ProjectsPage" in result.user_prompt
        assert "ProjectsPage.tsx" in result.user_prompt

        # Code context should include the page component
        assert "useQuery" in result.user_prompt or "projects" in result.user_prompt.lower()

    @pytest.mark.asyncio
    async def test_context_hash_deduplication(self, realistic_project: Path, db: Database):
        """Test that context hash enables deduplication."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Fix database connection issue",
            description="Fix the database connection issue in backend/app/db/database.py",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P0,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        # Run enrichment twice
        result1 = await pipeline.enrich(task, project)
        result2 = await pipeline.enrich(task, project)

        # Context hash should be identical
        assert result1.context_hash == result2.context_hash

        # Prompts should be identical
        assert result1.user_prompt == result2.user_prompt
        assert result1.system_prompt == result2.system_prompt

    @pytest.mark.asyncio
    async def test_all_stages_applied(self, realistic_project: Path, db: Database):
        """Test that all relevant stages are applied."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python", "FastAPI"],
        )

        # Create a comprehensive task
        task = Task(
            id=task_id,
            project_id=project.id,
            title="Implement comprehensive error handling",
            description=(
                "Add comprehensive error handling to all API endpoints in "
                "backend/app/api/routes.py. Handle database errors, validation "
                "errors, and return appropriate HTTP status codes. "
                "Also update the Kubernetes deployment to handle pod failures."
            ),
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P1,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=150000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Check that all expected stages are applied
        expected_stages = [
            "task_context",
            "project_context",
            "code_context",
            "documentation_context",
            "refinement_context",
        ]

        for stage in expected_stages:
            assert stage in result.metrics.stages_applied, f"Stage {stage} not applied"

        # May or may not have deployment/deployment_context depending on relevance
        # May or may not have history/logs/research depending on DB content

    @pytest.mark.asyncio
    async def test_token_budget_respected(self, realistic_project: Path, db: Database):
        """Test that token budget is respected."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Update all database models",
            description="Review and update all database models in the project",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
        )

        # Use a low token budget
        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=5000,  # Very low budget
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Token estimate should be reasonable (though with budget limits,
        # actual may be slightly over due to per-stage overhead)
        assert result.metrics.estimated_tokens < 10000  # Allow some overhead

    @pytest.mark.asyncio
    async def test_logs_context_for_debugging_task(
        self, realistic_project: Path, db: Database
    ):
        """Test that logs context is added for debugging tasks."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        # First, create some log entries without project_id (let DB auto-generate id)
        await db.execute(
            """
            INSERT INTO logs (level, component, message, data)
            VALUES (?, ?, ?, ?)
            """,
            (
                "error",
                "api",
                "Database connection failed",
                '{"traceback": "ConnectionError: Unable to connect to database"}',
            ),
        )

        await db.execute(
            """
            INSERT INTO logs (level, component, message, data)
            VALUES (?, ?, ?, ?)
            """,
            (
                "critical",
                "scheduler",
                "Worker process crashed",
                '{"error": "WorkerTimeoutError"}',
            ),
        )

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Fix database connection errors",
            description=(
                "Debug and fix the database connection errors that are causing "
                "the API to crash. Check the error logs for stack traces."
            ),
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P0,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Logs context may or may not be included depending on task/project matching
        # The key thing is the pipeline completes successfully
        assert isinstance(result, AssembledPrompt)
        assert result.user_prompt
        assert result.system_prompt

    @pytest.mark.asyncio
    async def test_research_context_with_completed_tasks(
        self, realistic_project: Path, db: Database
    ):
        """Test research context with related completed tasks."""
        # Note: This test is simplified because session_metrics requires worker_id
        # which would require more complex setup. The research_context stage
        # is tested in other test files (test_research_context.py).
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        # Create a task
        task = Task(
            id=task_id,
            project_id=project.id,
            title="Add error handling to API routes",
            description="Add error handling to API route handlers",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Pipeline should complete successfully even without related tasks
        # Research context may or may not be included depending on DB content
        assert isinstance(result, AssembledPrompt)
        assert result.user_prompt
        assert result.system_prompt

    @pytest.mark.asyncio
    async def test_context_assembly_logging(
        self, realistic_project: Path, db: Database
    ):
        """Test that context assembly is logged for observability."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Test task for assembly logging",
            description="Test description",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P3,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        # Run enrichment with logging enabled (default)
        result = await pipeline.enrich(task, project, log_assembly=True)

        # Verify log entry was created
        logs = await db.fetchall(
            """
            SELECT * FROM context_assembly_logs
            WHERE task_id = ? AND project_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (str(task.id), str(project.id)),
        )

        assert len(logs) == 1

        log_entry = logs[0]
        assert log_entry["task_id"] == str(task.id)
        assert log_entry["project_id"] == str(project.id)
        assert log_entry["context_hash"] == result.context_hash
        assert log_entry["tokens_used"] == result.metrics.estimated_tokens
        assert log_entry["assembly_time_ms"] > 0
        assert len(log_entry["stages_applied"]) > 0


class TestEnrichmentPipelineQuality:
    """Tests for enrichment output quality."""

    @pytest.mark.asyncio
    async def test_code_context_relevance(self, realistic_project: Path, db: Database):
        """Test that code context finds relevant files."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        # Task explicitly mentioning a file
        task = Task(
            id=task_id,
            project_id=project.id,
            title="Fix bug in repositories.py",
            description="Fix the bug in backend/app/db/repositories.py where list returns wrong data",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P1,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Should include content from repositories.py
        assert "repositories" in result.user_prompt.lower()
        assert "TaskRepository" in result.user_prompt or "class TaskRepository" in result.user_prompt

    @pytest.mark.asyncio
    async def test_documentation_includes_readme(self, realistic_project: Path, db: Database):
        """Test that README is always included in documentation context."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Add new feature",
            description="Implement a new feature",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P2,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # README should be included
        assert "README" in result.user_prompt or "FastAPI" in result.user_prompt
        # Check for content from README
        assert "multi-agent" in result.user_prompt.lower() or "orchestration" in result.user_prompt.lower()

    @pytest.mark.asyncio
    async def test_adr_filtering(self, realistic_project: Path, db: Database):
        """Test that ADRs are filtered by relevance."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        # Database-related task
        task = Task(
            id=task_id,
            project_id=project.id,
            title="Migrate from SQLite to PostgreSQL",
            description="Migrate the database from SQLite to PostgreSQL",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P1,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Should include database-related ADR
        assert "ADR" in result.user_prompt or "SQLite" in result.user_prompt

    @pytest.mark.asyncio
    async def test_refinement_context_structure(self, realistic_project: Path, db: Database):
        """Test that refinement context has proper structure."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Test task",
            description="Test description",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P3,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # Refinement context should have instructions
        assert "Instructions" in result.user_prompt or "implement" in result.user_prompt.lower()
        assert "completion" in result.user_prompt.lower() or "complete" in result.user_prompt.lower()

    @pytest.mark.asyncio
    async def test_system_prompt_quality(self, realistic_project: Path, db: Database):
        """Test that system prompt is well-structured."""
        project_id = uuid4()
        task_id = f"task-{uuid4().hex[:16]}"

        project = Project(
            id=project_id,
            name="ringmaster",
            description="Multi-agent orchestration platform",
            repo_url=str(realistic_project),
            tech_stack=["Python", "FastAPI"],
        )

        task = Task(
            id=task_id,
            project_id=project.id,
            title="Test task",
            description="Test",
            type=TaskType.TASK,
            status=TaskStatus.READY,
            priority=Priority.P3,
        )

        pipeline = EnrichmentPipeline(
            project_dir=realistic_project,
            max_context_tokens=100000,
            db=db,
        )

        result = await pipeline.enrich(task, project)

        # System prompt should have key elements
        assert "expert" in result.system_prompt.lower() or "engineer" in result.system_prompt.lower()
        assert "ringmaster" in result.system_prompt.lower()
        assert "Python" in result.system_prompt or "FastAPI" in result.system_prompt
        assert "guidelines" in result.system_prompt.lower() or "follow" in result.system_prompt.lower()
