"""Graph API routes for task dependency visualization."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ringmaster.api.deps import get_db
from ringmaster.db import Database, TaskRepository
from ringmaster.domain import TaskStatus, TaskType

router = APIRouter()


class GraphNode(BaseModel):
    """A node in the dependency graph."""

    id: str
    title: str
    task_type: str
    status: str
    priority: str
    parent_id: str | None = None
    pagerank_score: float = 0.0
    on_critical_path: bool = False


class GraphEdge(BaseModel):
    """An edge (dependency) in the graph."""

    source: str  # parent_id (dependency)
    target: str  # child_id (depends on parent)


class GraphData(BaseModel):
    """Complete graph data for visualization."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: dict[str, int]


@router.get("")
async def get_dependency_graph(
    db: Annotated[Database, Depends(get_db)],
    project_id: UUID,
    include_done: bool = Query(default=False, description="Include completed tasks"),
    include_subtasks: bool = Query(default=True, description="Include subtasks"),
) -> GraphData:
    """Get the task dependency graph for a project.

    Returns nodes (tasks) and edges (dependencies) suitable for graph visualization.
    Optionally filters out completed tasks and subtasks.
    """
    repo = TaskRepository(db)

    # Get all tasks for the project
    tasks = await repo.list_tasks(project_id=project_id, limit=1000)

    # Filter by completion status
    if not include_done:
        tasks = [t for t in tasks if t.status != TaskStatus.DONE]

    # Filter by task type
    if not include_subtasks:
        tasks = [t for t in tasks if t.type != TaskType.SUBTASK]

    # Build nodes
    task_ids = {t.id for t in tasks}
    nodes = []
    for task in tasks:
        nodes.append(
            GraphNode(
                id=task.id,
                title=task.title,
                task_type=task.type.value,
                status=task.status.value,
                priority=task.priority.value,
                parent_id=getattr(task, "parent_id", None),
                pagerank_score=getattr(task, "pagerank_score", 0.0),
                on_critical_path=getattr(task, "on_critical_path", False),
            )
        )

    # Get all dependencies
    edges = []
    for task in tasks:
        deps = await repo.get_dependencies(task.id)
        for dep in deps:
            # Only include edges where both nodes are in our set
            if dep.parent_id in task_ids and dep.child_id in task_ids:
                edges.append(GraphEdge(source=dep.parent_id, target=dep.child_id))

    # Add parent-child relationships (epic -> task, task -> subtask)
    for task in tasks:
        parent_id = getattr(task, "parent_id", None)
        if parent_id and parent_id in task_ids:
            # Check if this edge doesn't already exist
            edge_exists = any(
                e.source == parent_id and e.target == task.id for e in edges
            )
            if not edge_exists:
                edges.append(GraphEdge(source=parent_id, target=task.id))

    # Compute stats
    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for task in tasks:
        status = task.status.value
        status_counts[status] = status_counts.get(status, 0) + 1
        task_type = task.type.value
        type_counts[task_type] = type_counts.get(task_type, 0) + 1

    stats = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        **{f"status_{k}": v for k, v in status_counts.items()},
        **{f"type_{k}": v for k, v in type_counts.items()},
    }

    return GraphData(nodes=nodes, edges=edges, stats=stats)
