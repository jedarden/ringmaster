"""Ringmaster CLI entry point."""

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Ringmaster - Multi-Coding-Agent Orchestration Platform."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8080, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the Ringmaster API server."""
    import uvicorn

    console.print(f"[bold green]Starting Ringmaster API server on {host}:{port}[/bold green]")

    uvicorn.run(
        "ringmaster.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@cli.command()
@click.option("--max-concurrent", default=4, help="Maximum concurrent tasks")
@click.option("--poll-interval", default=2.0, help="Queue poll interval in seconds")
def scheduler(max_concurrent: int, poll_interval: float) -> None:
    """Start the task scheduler."""
    from ringmaster.db import get_database
    from ringmaster.scheduler import Scheduler

    async def run_scheduler() -> None:
        db = await get_database()
        sched = Scheduler(
            db,
            max_concurrent_tasks=max_concurrent,
            poll_interval=poll_interval,
        )
        console.print("[bold green]Starting scheduler...[/bold green]")
        await sched.start()

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            await sched.stop()

    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped[/yellow]")


@cli.command()
@click.option("--db-path", type=click.Path(), help="Database path")
def init(db_path: str | None) -> None:
    """Initialize Ringmaster database and directories."""
    from ringmaster.db import get_database

    async def do_init() -> None:
        path = Path(db_path) if db_path else None
        db = await get_database(path)
        console.print(f"[green]Database initialized at {db.db_path}[/green]")

    asyncio.run(do_init())


@cli.command()
def status() -> None:
    """Show Ringmaster status."""
    from ringmaster.db import get_database
    from ringmaster.queue import QueueManager

    async def show_status() -> None:
        db = await get_database()
        manager = QueueManager(db)
        stats = await manager.get_queue_stats()

        table = Table(title="Ringmaster Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Ready Tasks", str(stats["ready_tasks"]))
        table.add_row("Assigned Tasks", str(stats["assigned_tasks"]))
        table.add_row("In Progress", str(stats["in_progress_tasks"]))
        table.add_row("Idle Workers", str(stats["idle_workers"]))
        table.add_row("Busy Workers", str(stats["busy_workers"]))

        console.print(table)

    asyncio.run(show_status())


@cli.group()
def project() -> None:
    """Manage projects."""
    pass


@project.command("list")
def project_list() -> None:
    """List all projects."""
    from ringmaster.db import ProjectRepository, get_database

    async def do_list() -> None:
        db = await get_database()
        repo = ProjectRepository(db)
        projects = await repo.list()

        if not projects:
            console.print("[yellow]No projects found[/yellow]")
            return

        table = Table(title="Projects")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Tech Stack")
        table.add_column("Created")

        for p in projects:
            table.add_row(
                str(p.id)[:8],
                p.name,
                ", ".join(p.tech_stack) if p.tech_stack else "-",
                p.created_at.strftime("%Y-%m-%d"),
            )

        console.print(table)

    asyncio.run(do_list())


@project.command("create")
@click.argument("name")
@click.option("--description", "-d", help="Project description")
@click.option("--tech-stack", "-t", multiple=True, help="Tech stack items")
@click.option("--repo-url", "-r", help="Repository URL")
def project_create(
    name: str,
    description: str | None,
    tech_stack: tuple[str, ...],
    repo_url: str | None,
) -> None:
    """Create a new project."""
    from ringmaster.db import ProjectRepository, get_database
    from ringmaster.domain import Project

    async def do_create() -> None:
        db = await get_database()
        repo = ProjectRepository(db)
        project = Project(
            name=name,
            description=description,
            tech_stack=list(tech_stack),
            repo_url=repo_url,
        )
        created = await repo.create(project)
        console.print(f"[green]Created project: {created.name} ({created.id})[/green]")

    asyncio.run(do_create())


@cli.group()
def task() -> None:
    """Manage tasks."""
    pass


@task.command("list")
@click.option("--project", "-p", help="Filter by project ID")
@click.option("--status", "-s", help="Filter by status")
def task_list(project: str | None, status: str | None) -> None:
    """List tasks."""
    from uuid import UUID

    from ringmaster.db import TaskRepository, get_database
    from ringmaster.domain import TaskStatus

    async def do_list() -> None:
        db = await get_database()
        repo = TaskRepository(db)

        project_id = UUID(project) if project else None
        task_status = TaskStatus(status) if status else None

        tasks = await repo.list_tasks(project_id=project_id, status=task_status)

        if not tasks:
            console.print("[yellow]No tasks found[/yellow]")
            return

        table = Table(title="Tasks")
        table.add_column("ID", style="dim")
        table.add_column("Title", style="cyan")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Priority")

        for t in tasks:
            status_color = {
                "done": "green",
                "failed": "red",
                "in_progress": "yellow",
                "ready": "blue",
            }.get(t.status.value, "white")

            table.add_row(
                t.id[:12],
                t.title[:40],
                t.type.value,
                f"[{status_color}]{t.status.value}[/{status_color}]",
                t.priority.value,
            )

        console.print(table)

    asyncio.run(do_list())


@task.command("create")
@click.argument("project_id")
@click.argument("title")
@click.option("--description", "-d", help="Task description")
@click.option("--priority", "-p", default="P2", help="Priority (P0-P4)")
def task_create(
    project_id: str,
    title: str,
    description: str | None,
    priority: str,
) -> None:
    """Create a new task."""
    from uuid import UUID

    from ringmaster.db import TaskRepository, get_database
    from ringmaster.domain import Priority, Task

    async def do_create() -> None:
        db = await get_database()
        repo = TaskRepository(db)
        task = Task(
            project_id=UUID(project_id),
            title=title,
            description=description,
            priority=Priority(priority),
        )
        created = await repo.create_task(task)
        console.print(f"[green]Created task: {created.title} ({created.id})[/green]")

    asyncio.run(do_create())


@task.command("enqueue")
@click.argument("task_id")
def task_enqueue(task_id: str) -> None:
    """Mark a task as ready for execution."""
    from ringmaster.db import get_database
    from ringmaster.queue import QueueManager

    async def do_enqueue() -> None:
        db = await get_database()
        manager = QueueManager(db)
        success = await manager.enqueue_task(task_id)
        if success:
            console.print(f"[green]Task {task_id} enqueued[/green]")
        else:
            console.print(f"[red]Failed to enqueue task {task_id}[/red]")
            console.print("Check if task exists and dependencies are met.")

    asyncio.run(do_enqueue())


@cli.group()
def worker() -> None:
    """Manage workers."""
    pass


@worker.command("list")
def worker_list() -> None:
    """List all workers."""
    from ringmaster.db import WorkerRepository, get_database

    async def do_list() -> None:
        db = await get_database()
        repo = WorkerRepository(db)
        workers = await repo.list()

        if not workers:
            console.print("[yellow]No workers found[/yellow]")
            return

        table = Table(title="Workers")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Tasks Done")

        for w in workers:
            status_color = {
                "idle": "green",
                "busy": "yellow",
                "offline": "red",
            }.get(w.status.value, "white")

            table.add_row(
                w.id[:12],
                w.name,
                w.type,
                f"[{status_color}]{w.status.value}[/{status_color}]",
                str(w.tasks_completed),
            )

        console.print(table)

    asyncio.run(do_list())


@worker.command("add")
@click.argument("name")
@click.option("--type", "-t", "worker_type", default="claude-code", help="Worker type")
@click.option("--command", "-c", default="claude", help="Command to run")
def worker_add(name: str, worker_type: str, command: str) -> None:
    """Add a new worker."""
    from ringmaster.db import WorkerRepository, get_database
    from ringmaster.domain import Worker

    async def do_add() -> None:
        db = await get_database()
        repo = WorkerRepository(db)
        worker = Worker(
            name=name,
            type=worker_type,
            command=command,
        )
        created = await repo.create(worker)
        console.print(f"[green]Added worker: {created.name} ({created.id})[/green]")

    asyncio.run(do_add())


@worker.command("activate")
@click.argument("worker_id")
def worker_activate(worker_id: str) -> None:
    """Activate a worker (mark as idle)."""
    from ringmaster.db import WorkerRepository, get_database
    from ringmaster.domain import WorkerStatus

    async def do_activate() -> None:
        db = await get_database()
        repo = WorkerRepository(db)
        worker = await repo.get(worker_id)
        if not worker:
            console.print(f"[red]Worker {worker_id} not found[/red]")
            return
        worker.status = WorkerStatus.IDLE
        await repo.update(worker)
        console.print(f"[green]Worker {worker_id} activated[/green]")

    asyncio.run(do_activate())


@cli.command()
def doctor() -> None:
    """Check system health and worker availability."""
    from ringmaster.worker.platforms import WORKER_REGISTRY

    console.print("[bold]Ringmaster Doctor[/bold]\n")

    async def check_workers() -> None:
        for name, worker_class in WORKER_REGISTRY.items():
            worker = worker_class()
            available = await worker.is_available()
            if available:
                console.print(f"  [green]✓[/green] {name}: available")
            else:
                console.print(f"  [red]✗[/red] {name}: not found")

    console.print("Checking workers:")
    asyncio.run(check_workers())

    # Check database
    console.print("\nChecking database:")
    try:
        from ringmaster.db import get_database

        async def check_db() -> None:
            db = await get_database()
            console.print(f"  [green]✓[/green] Database: {db.db_path}")

        asyncio.run(check_db())
    except Exception as e:
        console.print(f"  [red]✗[/red] Database: {e}")


# =============================================================================
# Worker Script Commands (for bash-based workers)
# =============================================================================


@cli.command("pull-bead")
@click.argument("worker_id")
@click.option(
    "--capabilities",
    "-c",
    multiple=True,
    help="Capabilities this worker has (e.g., python, rust)",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def pull_bead(worker_id: str, capabilities: tuple[str, ...], as_json: bool) -> None:
    """Pull the next available task for a worker.

    Used by external worker scripts to claim tasks from the queue.
    Outputs task JSON if available, or nothing if no tasks ready.
    """
    import json as json_lib

    from ringmaster.db import (
        ProjectRepository,
        TaskRepository,
        WorkerRepository,
        get_database,
    )
    from ringmaster.domain import TaskStatus, WorkerStatus

    async def do_pull() -> None:
        db = await get_database()
        worker_repo = WorkerRepository(db)
        task_repo = TaskRepository(db)
        project_repo = ProjectRepository(db)

        # Get or verify worker
        worker = await worker_repo.get(worker_id)
        if not worker:
            if not as_json:
                console.print(f"[red]Worker {worker_id} not found[/red]", err=True)
            return

        # Worker must be idle to pull
        if worker.status != WorkerStatus.IDLE:
            if not as_json:
                console.print(
                    f"[yellow]Worker {worker_id} is not idle[/yellow]", err=True
                )
            return

        # Get worker capabilities
        worker_caps = set(capabilities) if capabilities else set(worker.capabilities or [])

        # Get ready tasks ordered by priority
        ready_tasks = await task_repo.get_ready_tasks()
        if not ready_tasks:
            return  # No output means no tasks

        # Find first task matching capabilities
        for task in ready_tasks:
            required_caps = set(task.required_capabilities or [])
            if required_caps.issubset(worker_caps):
                # Claim the task
                from datetime import UTC, datetime

                task.status = TaskStatus.ASSIGNED
                task.worker_id = worker_id
                task.updated_at = datetime.now(UTC)
                await task_repo.update_task(task)

                # Update worker
                worker.status = WorkerStatus.BUSY
                worker.current_task_id = task.id
                worker.last_active_at = datetime.now(UTC)
                await worker_repo.update(worker)

                # Get project info
                project = await project_repo.get(task.project_id)

                # Output task info
                task_data = {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "priority": task.priority.value,
                    "type": task.type.value,
                    "attempt": task.attempts + 1,
                    "max_attempts": task.max_attempts,
                    "project_id": str(task.project_id),
                    "project_name": project.name if project else None,
                }

                if as_json:
                    print(json_lib.dumps(task_data))
                else:
                    console.print(f"[green]Claimed task:[/green] {task.id}")
                    console.print(f"  Title: {task.title}")
                    console.print(f"  Attempt: {task.attempts + 1}/{task.max_attempts}")
                    if project:
                        console.print(f"  Project: {project.name}")
                return

        # No matching task found
        if not as_json:
            console.print("[yellow]No tasks matching capabilities[/yellow]", err=True)

    asyncio.run(do_pull())


@cli.command("build-prompt")
@click.argument("task_id")
@click.option("--output", "-o", type=click.Path(), help="Write prompt to file")
@click.option("--project-dir", "-d", type=click.Path(exists=True), help="Project directory")
def build_prompt(task_id: str, output: str | None, project_dir: str | None) -> None:
    """Build an enriched prompt for a task.

    Assembles the full context including:
    - Task details and requirements
    - Project context
    - Relevant code files
    - Deployment context (if applicable)
    - Chat history (if available)
    - Instructions and completion signals
    """
    from ringmaster.db import ProjectRepository, TaskRepository, get_database
    from ringmaster.enricher.pipeline import EnrichmentPipeline

    async def do_build() -> None:
        db = await get_database()
        task_repo = TaskRepository(db)
        project_repo = ProjectRepository(db)

        # Get task
        task = await task_repo.get_task(task_id)
        if not task:
            console.print(f"[red]Task {task_id} not found[/red]", err=True)
            raise SystemExit(1)

        # Get project
        project = await project_repo.get(task.project_id)
        if not project:
            console.print("[red]Project not found for task[/red]", err=True)
            raise SystemExit(1)

        # Determine project directory
        proj_dir = Path(project_dir) if project_dir else None
        if proj_dir is None and project.repo_url:
            # Try common paths
            for base in [Path("/workspace"), Path.home() / "workspace", Path.cwd()]:
                candidate = base / project.name.lower().replace(" ", "-")
                if candidate.exists():
                    proj_dir = candidate
                    break
        if proj_dir is None:
            proj_dir = Path.cwd()

        # Create pipeline and enrich
        pipeline = EnrichmentPipeline(project_dir=proj_dir, db=db)
        assembled = await pipeline.enrich(task, project)

        # Format full prompt
        full_prompt = f"""# System Prompt

{assembled.system_prompt}

# User Prompt

{assembled.user_prompt}
"""

        # Output
        if output:
            output_path = Path(output)
            output_path.write_text(full_prompt)
            console.print(f"[green]Prompt written to {output_path}[/green]")
            console.print(f"  Context hash: {assembled.context_hash}")
            console.print(f"  Estimated tokens: ~{assembled.metrics.estimated_tokens}")
        else:
            print(full_prompt)

    asyncio.run(do_build())


@cli.command("report-result")
@click.argument("task_id")
@click.option("--status", "-s", required=True, type=click.Choice(["completed", "failed"]))
@click.option("--exit-code", "-e", type=int, default=0, help="Exit code from worker")
@click.option("--output-path", "-o", type=click.Path(), help="Path to output file")
@click.option("--reason", "-r", help="Failure reason (for failed status)")
def report_result(
    task_id: str,
    status: str,
    exit_code: int,
    output_path: str | None,
    reason: str | None,
) -> None:
    """Report task completion result.

    Called by external workers to report success or failure.
    """
    from datetime import UTC, datetime

    from ringmaster.db import TaskRepository, WorkerRepository, get_database
    from ringmaster.domain import TaskStatus, WorkerStatus

    async def do_report() -> None:
        db = await get_database()
        task_repo = TaskRepository(db)
        worker_repo = WorkerRepository(db)

        # Get task
        task = await task_repo.get_task(task_id)
        if not task:
            console.print(f"[red]Task {task_id} not found[/red]", err=True)
            raise SystemExit(1)

        # Get worker if assigned
        worker = None
        if task.worker_id:
            worker = await worker_repo.get(task.worker_id)

        success = status == "completed"

        if success:
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now(UTC)
            # Clear retry tracking on success
            task.retry_after = None
            task.last_failure_reason = None
            if worker:
                worker.tasks_completed += 1
            console.print(f"[green]Task {task_id} marked as completed[/green]")
        else:
            task.attempts += 1
            task.last_failure_reason = reason

            if task.attempts >= task.max_attempts:
                task.status = TaskStatus.FAILED
                console.print(f"[red]Task {task_id} failed after {task.attempts} attempts[/red]")
            else:
                # Calculate retry backoff
                from ringmaster.worker.executor import calculate_retry_backoff

                task.retry_after = calculate_retry_backoff(task.attempts)
                task.status = TaskStatus.READY  # Retry
                console.print(
                    f"[yellow]Task {task_id} failed, will retry after backoff[/yellow]"
                )

            if worker:
                worker.tasks_failed += 1

        task.output_path = output_path
        task.worker_id = None
        task.updated_at = datetime.now(UTC)
        await task_repo.update_task(task)

        # Update worker to idle
        if worker:
            worker.status = WorkerStatus.IDLE
            worker.current_task_id = None
            worker.last_active_at = datetime.now(UTC)
            await worker_repo.update(worker)
            console.print(f"  Worker {worker.name} returned to idle")

        # Check if dependent tasks can be enqueued
        if success:
            dependents = await task_repo.get_dependents(task_id)
            for dep in dependents:
                # Check if all dependencies are done
                dep_task = await task_repo.get_task(dep.child_id)
                if dep_task:
                    all_deps_done = True
                    parent_deps = await task_repo.get_dependencies(dep.child_id)
                    for parent_dep in parent_deps:
                        parent = await task_repo.get_task(parent_dep.parent_id)
                        if parent and parent.status != TaskStatus.DONE:
                            all_deps_done = False
                            break

                    if all_deps_done and dep_task.status == TaskStatus.DRAFT:
                        dep_task.status = TaskStatus.READY
                        dep_task.updated_at = datetime.now(UTC)
                        await task_repo.update_task(dep_task)
                        console.print(f"  [green]Unblocked dependent task: {dep_task.title}[/green]")

    asyncio.run(do_report())


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
