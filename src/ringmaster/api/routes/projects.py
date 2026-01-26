"""Project API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, ProjectRepository
from ringmaster.domain import Project

router = APIRouter()


class ProjectCreate(BaseModel):
    """Request body for creating a project."""

    name: str
    description: str | None = None
    tech_stack: list[str] = []
    repo_url: str | None = None


class ProjectUpdate(BaseModel):
    """Request body for updating a project."""

    name: str | None = None
    description: str | None = None
    tech_stack: list[str] | None = None
    repo_url: str | None = None


@router.get("")
async def list_projects(
    db: Annotated[Database, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Project]:
    """List all projects."""
    repo = ProjectRepository(db)
    return await repo.list(limit=limit, offset=offset)


@router.post("", status_code=201)
async def create_project(
    db: Annotated[Database, Depends(get_db)],
    body: ProjectCreate,
) -> Project:
    """Create a new project."""
    repo = ProjectRepository(db)
    project = Project(
        name=body.name,
        description=body.description,
        tech_stack=body.tech_stack,
        repo_url=body.repo_url,
    )
    return await repo.create(project)


@router.get("/{project_id}")
async def get_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> Project:
    """Get a project by ID."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}")
async def update_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    body: ProjectUpdate,
) -> Project:
    """Update a project."""
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.tech_stack is not None:
        project.tech_stack = body.tech_stack
    if body.repo_url is not None:
        project.repo_url = body.repo_url

    return await repo.update(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
) -> None:
    """Delete a project."""
    repo = ProjectRepository(db)
    deleted = await repo.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
