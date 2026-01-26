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


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
