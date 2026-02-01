"""Ringmaster CLI entry point."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

__all__ = [
    "run_async",
    "setup_logging",
    "cli",
    "main",
]

console = Console()

# Type variable for async function return types
T = TypeVar("T")


def run_async(coro: Callable[[], Awaitable[T]]) -> T:
    """Run an async function with proper database cleanup.

    This ensures the database connection is properly closed after the
    async function completes, preventing hanging CLI commands due to
    aiosqlite's background thread.
    """
    from ringmaster.db import close_database

    async def wrapped() -> T:
        try:
            return await coro()
        finally:
            await close_database()

    return asyncio.run(wrapped())


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
@click.option("--launcher-script", "-L", type=click.Path(exists=True), help="Path to launcher script")
@click.option("--launcher-args", "-A", multiple=True, help="Additional arguments for launcher script")
def worker_add(
    name: str,
    worker_type: str,
    command: str,
    launcher_script: str | None,
    launcher_args: tuple[str, ...],
) -> None:
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
            launcher_script=launcher_script,
            launcher_args=list(launcher_args) if launcher_args else None,
        )
        created = await repo.create(worker)
        console.print(f"[green]Added worker: {created.name} ({created.id})[/green]")
        if created.uses_launcher_script:
            console.print(f"  Launcher: {created.launcher_script}")

    asyncio.run(do_add)


@worker.command("create")
@click.argument("description", required=False)
@click.option("--worker-id", "-i", help="Custom worker ID")
@click.option("--interactive", "-I", is_flag=True, help="Interactive mode")
def worker_create(
    description: str | None,
    worker_id: str | None,
    interactive: bool,
) -> None:
    """Create a worker from natural language description.

    Examples:
        ringmaster worker create "claude code with sonnet for python"
        ringmaster worker create "aider using claude-3.5-sonnet, good at refactoring"
        ringmaster worker create --interactive

    Or use -I for interactive mode to describe your worker in plain English.
    """
    from ringmaster.db import get_database, WorkerRepository
    from ringmaster.domain import Worker
    from ringmaster.worker.natural import (
        create_worker_from_description,
        parse_worker_description,
        suggest_worker_improvements,
    )

    if interactive:
        # Interactive mode - prompt for description
        console.print("\n[bold cyan]Describe your worker in natural language:[/bold cyan]")
        console.print("  Example: 'claude code with sonnet for python and typescript tasks'")
        console.print("  Example: 'aider using claude-3.5-sonnet for refactoring'\n")
        description = click.prompt("Worker description")

    if not description:
        console.print("[red]Error: description is required (use -I for interactive mode)[/red]")
        return

    # Parse the description
    console.print(f"\n[bold]Parsing:[/bold] {description}")
    parse_result = parse_worker_description(description)

    if not parse_result.success:
        console.print(f"[red]Could not understand description:[/red] {parse_result.error}")
        if parse_result.suggestions:
            console.print("\n[bold]Suggestions:[/bold]")
            for suggestion in parse_result.suggestions:
                console.print(f"  • {suggestion}")
        return

    # Show what we understood
    console.print(f"[green]Worker Type:[/green] {parse_result.worker_type}")
    console.print(f"[green]Model:[/green] {parse_result.model or 'default'}")
    if parse_result.capabilities:
        console.print(f"[green]Capabilities:[/green] {', '.join(parse_result.capabilities)}")

    # Generate worker ID if not provided
    if not worker_id:
        import uuid
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"

    # Create the worker
    async def do_create() -> None:
        db = await get_database()
        repo = WorkerRepository(db)

        # Check if worker already exists
        existing = await repo.get(worker_id)
        if existing:
            console.print(f"[yellow]Worker {worker_id} already exists. Updating...[/yellow]")
            existing.type = parse_result.worker_type
            existing.name = parse_result.description or existing.name
            existing.description = parse_result.description
            existing.capabilities = parse_result.capabilities
            await repo.update(existing)
            console.print(f"[green]Updated worker: {worker_id}[/green]")
        else:
            worker = Worker(
                id=worker_id,
                name=parse_result.description or f"{parse_result.worker_type} worker",
                description=parse_result.description,
                type=parse_result.worker_type,
                capabilities=parse_result.capabilities,
            )
            created = await repo.create(worker)
            console.print(f"[green]Created worker: {worker_id} ({created.name})[/green]")

        # Show suggestions
        suggestions = suggest_worker_improvements(description)
        if suggestions:
            console.print("\n[bold cyan]Tips for better descriptions:[/bold cyan]")
            for suggestion in suggestions:
                console.print(f"  • {suggestion}")

    asyncio.run(do_create())


@worker.command("types")
def worker_types() -> None:
    """List available worker types and their models."""
    from ringmaster.worker.natural import list_available_workers

    workers = list_available_workers()

    if not workers:
        console.print("[yellow]No workers found on this system[/yellow]")
        console.print("\nInstall workers to use them with Ringmaster:")
        console.print("  • Claude Code: https://github.com/anthropics/claude-code")
        console.print("  • Aider: https://github.com/Aider-AI/aider")
        return

    table = Table(title="Available Worker Types")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Available", style="yellow")
    table.add_column("Default Model")
    table.add_column("Available Models")

    for w in workers:
        available_str = "[green]Yes[/green]" if w.is_available() else "[red]No[/red]"
        default_model = w.default_model or "-"
        models = ", ".join(w.available_models[:3])  # Show first 3
        if len(w.available_models) > 3:
            models += "..."

        table.add_row(
            w.name,
            w.display_name,
            available_str,
            default_model,
            models,
        )

    console.print(table)

    console.print("\n[bold]Usage:[/bold]")
    console.print("  ringmaster worker create \"claude code with sonnet for python\"")
    console.print("  ringmaster worker create \"aider using claude-3.5-sonnet\"")


@worker.command("update")
@click.argument("worker_id")
@click.option("--name", "-n", help="Worker name")
@click.option("--type", "-t", "worker_type", help="Worker type")
@click.option("--command", "-c", help="Command to run")
@click.option("--launcher-script", "-L", type=click.Path(), help="Path to launcher script")
@click.option("--launcher-script-inline", help="Inline launcher script content")
@click.option("--launcher-args", "-A", multiple=True, help="Additional arguments for launcher script")
@click.option("--capabilities", "-c", multiple=True, help="Worker capabilities")
@click.option("--working-dir", "-w", type=click.Path(), help="Working directory")
@click.option("--timeout", "-T", type=int, help="Timeout in seconds")
def worker_update(
    worker_id: str,
    name: str | None,
    worker_type: str | None,
    command: str | None,
    launcher_script: str | None,
    launcher_script_inline: str | None,
    launcher_args: tuple[str, ...],
    capabilities: tuple[str, ...],
    working_dir: str | None,
    timeout: int | None,
) -> None:
    """Update an existing worker.

    Only specified fields will be updated. Use this to change a worker's
    configuration, capabilities, or launcher script.
    """
    from ringmaster.db import WorkerRepository, get_database
    from ringmaster.domain import Worker

    async def do_update() -> None:
        db = await get_database()
        repo = WorkerRepository(db)
        worker = await repo.get(worker_id)
        if not worker:
            console.print(f"[red]Worker {worker_id} not found[/red]")
            raise SystemExit(1)

        # Update fields that were provided
        if name is not None:
            worker.name = name
        if worker_type is not None:
            worker.type = worker_type
        if command is not None:
            worker.command = command
        if launcher_script is not None:
            worker.launcher_script = launcher_script
        if launcher_script_inline is not None:
            worker.launcher_script_inline = launcher_script_inline
        if launcher_args:
            worker.launcher_args = list(launcher_args)
        if capabilities:
            worker.capabilities = list(capabilities)
        if working_dir is not None:
            worker.working_dir = working_dir
        if timeout is not None:
            worker.timeout_seconds = timeout

        updated = await repo.update(worker)
        console.print(f"[green]Updated worker: {updated.name} ({updated.id})[/green]")
        if updated.uses_launcher_script:
            console.print(f"  Launcher: {updated.launcher_script}")
        console.print(f"  Type: {updated.type}")
        console.print(f"  Capabilities: {', '.join(updated.capabilities) or 'None'}")

    asyncio.run(do_update)


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


@worker.command("spawn")
@click.argument("worker_id")
@click.option("--type", "-t", "worker_type", default="claude-code", help="Worker type")
@click.option("--capabilities", "-c", multiple=True, help="Worker capabilities")
@click.option("--worktree", "-w", type=click.Path(), help="Git worktree path")
@click.option("--command", help="Custom command (for generic workers)")
@click.option("--launcher-script", "-L", type=click.Path(exists=True), help="Path to launcher script")
@click.option("--launcher-args", "-A", multiple=True, help="Additional arguments for launcher script")
@click.option("--log-dir", type=click.Path(), help="Log directory")
def worker_spawn(
    worker_id: str,
    worker_type: str,
    capabilities: tuple[str, ...],
    worktree: str | None,
    command: str | None,
    launcher_script: str | None,
    launcher_args: tuple[str, ...],
    log_dir: str | None,
) -> None:
    """Spawn a worker in a tmux session.

    Creates a new tmux session running a worker script that:
    - Polls for tasks via `ringmaster pull-bead`
    - Builds prompts via `ringmaster build-prompt`
    - Executes the worker CLI (claude, aider, etc.) OR custom launcher script
    - Reports results via `ringmaster report-result`

    Worker types: claude-code, aider, codex, goose, generic, launcher

    Use --launcher-script to run a custom script instead of built-in commands.
    The script will receive environment variables:
    - RINGMASTER_PROMPT_FILE: Path to file with the enriched prompt
    - RINGMASTER_WORKING_DIR: Working directory for the task
    - RINGMASTER_TASK_ID: Task/bead identifier
    - RINGMASTER_WORKER_ID: Worker identifier
    - RINGMASTER_LOG_FILE: Path to worker log file
    """
    from ringmaster.db import WorkerRepository, get_database
    from ringmaster.domain import Worker, WorkerStatus
    from ringmaster.worker.spawner import WorkerSpawner

    async def do_spawn() -> None:
        db = await get_database()
        worker_repo = WorkerRepository(db)

        # Check if worker exists in DB, create if not
        worker = await worker_repo.get(worker_id)
        if not worker:
            worker = Worker(
                id=worker_id,
                name=worker_id,
                type=worker_type,
                command=command or worker_type,
                capabilities=list(capabilities) if capabilities else [],
                launcher_script=launcher_script,
                launcher_args=list(launcher_args) if launcher_args else None,
            )
            await worker_repo.create(worker)
            console.print(f"[green]Created worker record: {worker_id}[/green]")
        else:
            # Update capabilities and launcher config if provided
            if capabilities:
                worker.capabilities = list(capabilities)
            if launcher_script is not None:
                worker.launcher_script = launcher_script
            if launcher_args:
                worker.launcher_args = list(launcher_args)
            await worker_repo.update(worker)

        # Create spawner
        spawner = WorkerSpawner(
            log_dir=Path(log_dir) if log_dir else None,
            db_path=db.db_path,
        )

        try:
            spawned = await spawner.spawn(
                worker_id=worker_id,
                worker_name=worker.name,
                worker_type=worker_type,
                capabilities=list(capabilities) if capabilities else worker.capabilities,
                generated_script=worker.generated_script,
            )

            # Update worker status
            worker.status = WorkerStatus.IDLE
            await worker_repo.update(worker)

            console.print(f"[green]Spawned worker {worker_id}[/green]")
            console.print(f"  Type: {spawned.worker_type}")
            console.print(f"  Session: {spawned.tmux_session}")
            console.print(f"  Log: {spawned.log_path}")
            if launcher_script or worker.launcher_script:
                console.print(f"  Launcher: {launcher_script or worker.launcher_script}")
            console.print(f"\nTo attach: [cyan]{spawner.attach_command(worker_id)}[/cyan]")

        except RuntimeError as e:
            console.print(f"[red]Failed to spawn worker: {e}[/red]")
            raise SystemExit(1) from e

    run_async(do_spawn)


@worker.command("attach")
@click.argument("worker_id")
def worker_attach(worker_id: str) -> None:
    """Show command to attach to a worker's tmux session."""
    from ringmaster.worker.spawner import WorkerSpawner

    spawner = WorkerSpawner()
    cmd = spawner.attach_command(worker_id)
    console.print(f"[cyan]{cmd}[/cyan]")
    console.print("\n[dim]Run the above command to attach to the worker session[/dim]")


@worker.command("kill")
@click.argument("worker_id")
@click.option("--force", "-f", is_flag=True, help="Force kill without confirmation")
def worker_kill(worker_id: str, force: bool) -> None:
    """Kill a worker's tmux session."""
    from ringmaster.db import WorkerRepository, get_database
    from ringmaster.domain import WorkerStatus
    from ringmaster.worker.spawner import WorkerSpawner

    async def do_kill() -> None:
        spawner = WorkerSpawner()

        # Check if running
        if not await spawner.is_running(worker_id):
            console.print(f"[yellow]Worker {worker_id} is not running[/yellow]")
            return

        if not force and not click.confirm(f"Kill worker {worker_id}?"):
            console.print("Aborted")
            return

        success = await spawner.kill(worker_id)
        if success:
            console.print(f"[green]Killed worker {worker_id}[/green]")

            # Update worker status in database
            db = await get_database()
            worker_repo = WorkerRepository(db)
            worker = await worker_repo.get(worker_id)
            if worker:
                worker.status = WorkerStatus.OFFLINE
                worker.current_task_id = None
                await worker_repo.update(worker)
                console.print("  Updated worker status to offline")
        else:
            console.print(f"[red]Failed to kill worker {worker_id}[/red]")

    asyncio.run(do_kill())


@worker.command("sessions")
def worker_sessions() -> None:
    """List all running worker tmux sessions."""
    from ringmaster.worker.spawner import WorkerSpawner

    async def do_list() -> None:
        spawner = WorkerSpawner()
        sessions = await spawner.list_sessions()

        if not sessions:
            console.print("[yellow]No running worker sessions[/yellow]")
            return

        table = Table(title="Worker Sessions")
        table.add_column("Session", style="cyan")
        table.add_column("Worker ID")
        table.add_column("Attach Command", style="dim")

        for session in sessions:
            # Extract worker ID from session name
            worker_id = session.replace("rm-worker-", "")
            table.add_row(
                session,
                worker_id,
                f"tmux attach -t {session}",
            )

        console.print(table)

    asyncio.run(do_list())


@worker.command("output")
@click.argument("worker_id")
@click.option("--lines", "-n", default=50, help="Number of lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
def worker_output(worker_id: str, lines: int, follow: bool) -> None:
    """Show recent output from a worker's log."""
    import subprocess as sp

    from ringmaster.worker.spawner import WorkerSpawner

    async def do_output() -> None:
        spawner = WorkerSpawner()
        log_path = spawner.log_dir / f"{worker_id}.log"

        if not log_path.exists():
            console.print(f"[yellow]No log file found for worker {worker_id}[/yellow]")
            return

        if follow:
            # Use tail -f for following
            console.print(f"[dim]Following {log_path}... (Ctrl+C to stop)[/dim]\n")
            sp.run(["tail", "-f", "-n", str(lines), str(log_path)])
        else:
            output = await spawner.get_output(worker_id, lines)
            if output:
                console.print(output)
            else:
                console.print("[yellow]No output available[/yellow]")

    asyncio.run(do_output())


@worker.command("prune-worktrees")
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option("--dry-run", is_flag=True, help="Show what would be pruned without actually pruning")
def worker_prune_worktrees(repo_path: str, dry_run: bool) -> None:
    """Prune stale worktrees for a repository.

    Removes worktrees whose directories no longer exist. This can happen
    when worker directories are deleted without using 'git worktree remove'.

    REPO_PATH defaults to the current directory.
    """
    from pathlib import Path

    from ringmaster.git.worktrees import clean_stale_worktrees, list_worktrees

    async def do_prune() -> None:
        repo = Path(repo_path).resolve()

        # First, list worktrees to show prunable ones
        worktrees = await list_worktrees(repo)
        prunable = [wt for wt in worktrees if wt.is_prunable]

        if not prunable:
            console.print("[green]No stale worktrees to prune[/green]")
            return

        console.print(f"[yellow]Found {len(prunable)} stale worktrees[/yellow]")
        for wt in prunable:
            console.print(f"  - {wt.path}")

        if dry_run:
            console.print("\n[dim]Dry run mode - no changes made[/dim]")
            return

        # Actually prune
        removed = await clean_stale_worktrees(repo)
        console.print(f"\n[green]Pruned {removed} stale worktrees[/green]")

    asyncio.run(do_prune())


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

    # Suppress logging when using JSON output to keep output clean
    if as_json:
        logging.getLogger().setLevel(logging.WARNING)

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

    run_async(do_pull)


@cli.command("build-prompt")
@click.argument("task_id")
@click.option("--output", "-o", type=click.Path(), help="Write prompt to file")
@click.option("--project-dir", "-d", type=click.Path(exists=True), help="Project directory")
@click.option("--quiet", "-q", is_flag=True, help="Suppress logging output")
def build_prompt(task_id: str, output: str | None, project_dir: str | None, quiet: bool) -> None:
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

    # Suppress logging when quiet or when writing to file (for script use)
    if quiet or output:
        logging.getLogger().setLevel(logging.WARNING)

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

    run_async(do_build)


@cli.command("report-result")
@click.argument("task_id")
@click.option("--status", "-s", required=True, type=click.Choice(["completed", "failed"]))
@click.option("--exit-code", "-e", type=int, default=0, help="Exit code from worker")
@click.option("--output-path", "-o", type=click.Path(), help="Path to output file")
@click.option("--reason", "-r", help="Failure reason (for failed status)")
@click.option("--changes-committed", is_flag=True, help="Worker committed code changes")
def report_result(
    task_id: str,
    status: str,
    exit_code: int,
    output_path: str | None,
    reason: str | None,
    changes_committed: bool,
) -> None:
    """Report task completion result.

    Called by external workers to report success or failure.
    If --changes-committed is set and changes affect ringmaster code,
    triggers hot-reload for self-improvement.
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

            # Handle self-improvement if changes were committed
            if changes_committed:
                await _handle_self_improvement(task_id)
        else:
            task.attempts += 1
            task.last_failure_reason = reason

            if task.attempts >= task.max_attempts:
                task.status = TaskStatus.FAILED
                console.print(f"[red]Task {task_id} failed after {task.attempts} attempts[/red]")
            else:
                # Calculate retry backoff
                from ringmaster.worker.executor import calculate_retry_backoff

                backoff = calculate_retry_backoff(task.attempts)
                task.retry_after = datetime.now(UTC) + backoff
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

            # Clean up task resources (worktree, branch, temp files)
            await _cleanup_task_resources(task_id, worker.id if worker else None)

    run_async(do_report)


async def _cleanup_task_resources(task_id: str, worker_id: str | None) -> None:
    """Clean up resources after task completion."""
    from ringmaster.cleanup import cleanup_task_resources

    try:
        stats = await cleanup_task_resources(task_id, worker_id)
        if stats.worktrees_removed or stats.branches_removed or stats.temp_files_removed:
            console.print(f"  [dim]Cleaned up: {stats.worktrees_removed} worktrees, "
                         f"{stats.branches_removed} branches, {stats.temp_files_removed} temp files[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Warning: cleanup failed: {e}[/yellow]")


async def _handle_self_improvement(task_id: str) -> None:
    """Handle self-improvement when code changes are committed.

    Checks if changes affect ringmaster code and triggers hot-reload.
    """
    import subprocess
    from pathlib import Path

    from ringmaster.reload import HotReloader, FileChange

    # Get the last commit's changed files
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print("[yellow]Could not determine changed files[/yellow]")
        return

    changed_files = result.stdout.strip().split("\n")
    ringmaster_files = [f for f in changed_files if "ringmaster" in f and f.endswith(".py")]

    if not ringmaster_files:
        console.print("  No ringmaster code changes, skipping hot-reload")
        return

    console.print(f"  [cyan]Self-improvement detected: {len(ringmaster_files)} ringmaster files changed[/cyan]")
    for f in ringmaster_files[:5]:  # Show first 5
        console.print(f"    - {f}")
    if len(ringmaster_files) > 5:
        console.print(f"    ... and {len(ringmaster_files) - 5} more")

    # Create file changes for hot-reload
    changes = [
        FileChange(path=Path(f), change_type="modified")
        for f in ringmaster_files
    ]

    # Run hot-reload
    reloader = HotReloader(project_root=Path.cwd())

    console.print("  [cyan]Running tests before hot-reload...[/cyan]")
    reload_result = await reloader.process_changes(changes)

    if reload_result.status.value == "success":
        console.print(f"  [green]Hot-reload successful: {len(reload_result.reloaded_modules)} modules reloaded[/green]")
    elif reload_result.status.value == "rolled_back":
        console.print(f"  [red]Tests failed, changes rolled back[/red]")
        if reload_result.test_output:
            # Show last few lines of test output
            lines = reload_result.test_output.strip().split("\n")
            for line in lines[-10:]:
                console.print(f"    {line}")
    else:
        console.print(f"  [red]Hot-reload failed: {reload_result.error_message}[/red]")


# =============================================================================
# Self-Update Commands
# =============================================================================


@cli.group()
def update() -> None:
    """Manage Ringmaster updates."""
    pass


@update.command("check")
@click.option("--force", "-f", is_flag=True, help="Bypass cache and check GitHub")
def update_check(force: bool) -> None:
    """Check for updates from GitHub releases."""
    from ringmaster.updater import check_for_updates

    result = check_for_updates(force=force)

    if result.status.value == "up_to_date":
        console.print(f"[green]✓[/green] {result.message}")
        console.print(f"  Current: [cyan]{result.current_version}[/cyan]")
    elif result.status.value == "update_available":
        console.print(f"[yellow]→[/yellow] {result.message}")
        console.print(f"  Current: [dim]{result.current_version}[/dim]")
        console.print(f"  Latest:  [cyan]{result.latest_version}[/cyan]")
        console.print("\nRun [cyan]ringmaster update apply[/cyan] to update")
    else:
        console.print(f"[red]✗[/red] {result.message}")
        if result.error:
            console.print(f"  [dim]{result.error}[/dim]")


@update.command("apply")
@click.option("--version", "-v", help="Specific version to install")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def update_apply(version: str | None, yes: bool) -> None:
    """Download and apply an update from GitHub releases.

    This will replace the current executable and restart Ringmaster.
    """
    from ringmaster.updater import (
        UpdateStatus,
        apply_update,
        check_for_updates,
        download_update,
    )

    current_version = check_for_updates().current_version

    # Check what update we're applying
    if version:
        console.print(f"Checking for version [cyan]{version}[/cyan]...")
    else:
        console.print("Checking for updates...")

    check_result = check_for_updates(force=True)

    if version and check_result.latest_version != version:
        console.print(f"[yellow]Warning: Version {version} not found in latest releases[/yellow]")
        console.print("Attempting to download anyway...")

    if check_result.status.value == "up_to_date" and not version:
        console.print("[green]Already up to date![/green]")
        console.print(f"  Current version: [cyan]{current_version}[/cyan]")
        return

    if check_result.status.value == "update_available":
        console.print(f"Update available: [cyan]{check_result.latest_version}[/cyan]")
    elif version:
        console.print(f"Downloading version: [cyan]{version}[/cyan]")

    # Confirm
    if not yes:
        latest = version or check_result.latest_version
        if not click.confirm(f"Update Ringmaster {current_version} → {latest}?"):
            console.print("Aborted")
            return

    # Download
    console.print("Downloading update...")
    downloaded_path = download_update(version)

    if not downloaded_path:
        console.print("[red]Failed to download update[/red]")
        console.print("[dim]No pre-built binary available for this platform[/dim]")
        console.print("\nYou can install Ringmaster manually:")
        console.print("  pip install --upgrade ringmaster")
        raise SystemExit(1)

    console.print("  Downloaded: [dim]" + str(downloaded_path) + "[/dim]")

    # Apply update
    console.print("Applying update...")
    apply_result = apply_update(downloaded_path)

    if apply_result.status == UpdateStatus.SUCCESS:
        console.print("[green]✓[/green] Update applied successfully!")
        console.print("  Restart Ringmaster to use the new version")
        console.print("\nTo restart now, run:")
        console.print("  [cyan]ringmaster update restart[/cyan]")

        if apply_result.backup_path:
            console.print(f"\nBackup saved to: [dim]{apply_result.backup_path}[/dim]")
    else:
        console.print(f"[red]✗[/red] {apply_result.message}")
        if apply_result.error:
            console.print(f"  Error: {apply_result.error}")
        if apply_result.backup_path:
            console.print(f"  Backup available at: {apply_result.backup_path}")
        raise SystemExit(1)


@update.command("restart")
@click.argument("args", nargs=-1)
def update_restart(args: tuple[str, ...]) -> None:
    """Restart Ringmaster with the updated version.

    Any additional arguments are passed to the new process.
    """
    from ringmaster.updater import restart_with_new_version

    console.print("[yellow]Restarting Ringmaster...[/yellow]")

    args_list = list(args) if args else None
    restart_with_new_version(args_list)


@update.command("rollback")
@click.option("--backup", "-b", type=click.Path(), help="Path to backup file")
def update_rollback(backup: str | None) -> None:
    """Rollback to a previous version using backup."""
    from pathlib import Path

    from ringmaster.updater import rollback

    backup_path = Path(backup) if backup else None

    if rollback(backup_path):
        console.print("[green]✓[/green] Rollback successful!")
        console.print("Restart Ringmaster to use the previous version")
    else:
        console.print("[red]✗[/red] Rollback failed")
        console.print("[dim]No backup found or restore failed[/dim]")
        raise SystemExit(1)


# =============================================================================
# Cleanup Commands
# =============================================================================


@cli.group()
def cleanup() -> None:
    """Clean up resources (worktrees, branches, temp files)."""
    pass


@cleanup.command("status")
def cleanup_status() -> None:
    """Show current resource usage."""
    from ringmaster.cleanup import ResourceCleaner

    async def do_status() -> None:
        cleaner = ResourceCleaner()
        status = await cleaner.get_status()

        console.print("[bold]Resource Usage[/bold]\n")

        # Worktrees
        wt = status["worktrees"]
        wt_size = wt["bytes"] / (1024 * 1024)  # MB
        console.print(f"  Worktrees:   {wt['count']:3d}  ({wt_size:.1f} MB)")

        # Branches
        br = status["branches"]
        console.print(f"  Branches:    {br['count']:3d}")

        # Temp files
        tf = status["temp_files"]
        tf_size = tf["bytes"] / 1024  # KB
        console.print(f"  Temp files:  {tf['count']:3d}  ({tf_size:.1f} KB)")

        # Scripts
        sc = status["scripts"]
        sc_size = sc["bytes"] / 1024  # KB
        console.print(f"  Scripts:     {sc['count']:3d}  ({sc_size:.1f} KB)")

        total_mb = (wt["bytes"] + tf["bytes"] + sc["bytes"]) / (1024 * 1024)
        console.print(f"\n  [bold]Total:     {total_mb:.1f} MB[/bold]")

    asyncio.run(do_status())


@cleanup.command("worktrees")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def cleanup_worktrees(dry_run: bool, force: bool) -> None:
    """Remove stale git worktrees."""
    from ringmaster.cleanup import ResourceCleaner

    async def do_cleanup() -> None:
        cleaner = ResourceCleaner()
        status = await cleaner.get_status()

        if status["worktrees"]["count"] == 0:
            console.print("[green]No worktrees to clean up[/green]")
            return

        size_mb = status["worktrees"]["bytes"] / (1024 * 1024)
        console.print(f"Found {status['worktrees']['count']} worktrees ({size_mb:.1f} MB)")

        if dry_run:
            console.print("[dim]Dry run - no changes made[/dim]")
            return

        if not force and not click.confirm("Remove all stale worktrees?"):
            console.print("Aborted")
            return

        stats = await cleaner.cleanup_stale_worktrees()
        console.print(f"[green]Removed {stats.worktrees_removed} worktrees[/green]")
        if stats.bytes_freed:
            console.print(f"  Freed {stats.bytes_freed / (1024 * 1024):.1f} MB")
        for error in stats.errors:
            console.print(f"  [red]Error:[/red] {error}")

    asyncio.run(do_cleanup())


@cleanup.command("branches")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def cleanup_branches(dry_run: bool, force: bool) -> None:
    """Remove orphaned ringmaster/bd-* branches."""
    from ringmaster.cleanup import ResourceCleaner

    async def do_cleanup() -> None:
        cleaner = ResourceCleaner()
        status = await cleaner.get_status()

        if status["branches"]["count"] == 0:
            console.print("[green]No orphan branches to clean up[/green]")
            return

        console.print(f"Found {status['branches']['count']} ringmaster branches")

        if dry_run:
            console.print("[dim]Dry run - no changes made[/dim]")
            return

        if not force and not click.confirm("Remove orphaned branches?"):
            console.print("Aborted")
            return

        stats = await cleaner.cleanup_stale_branches()
        console.print(f"[green]Removed {stats.branches_removed} branches[/green]")
        for error in stats.errors:
            console.print(f"  [red]Error:[/red] {error}")

    asyncio.run(do_cleanup())


@cleanup.command("temp")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def cleanup_temp(dry_run: bool, force: bool) -> None:
    """Remove stale temporary files."""
    from ringmaster.cleanup import ResourceCleaner

    async def do_cleanup() -> None:
        cleaner = ResourceCleaner()
        status = await cleaner.get_status()

        total = status["temp_files"]["count"] + status["scripts"]["count"]
        if total == 0:
            console.print("[green]No temp files to clean up[/green]")
            return

        console.print(f"Found {status['temp_files']['count']} temp files, {status['scripts']['count']} scripts")

        if dry_run:
            console.print("[dim]Dry run - no changes made[/dim]")
            return

        if not force and not click.confirm("Remove stale temp files?"):
            console.print("Aborted")
            return

        stats1 = await cleaner.cleanup_stale_temp_files()
        stats2 = await cleaner.cleanup_stale_scripts()
        stats = stats1 + stats2

        console.print(f"[green]Removed {stats.temp_files_removed} temp files, {stats.scripts_removed} scripts[/green]")
        if stats.bytes_freed:
            console.print(f"  Freed {stats.bytes_freed / 1024:.1f} KB")
        for error in stats.errors:
            console.print(f"  [red]Error:[/red] {error}")

    asyncio.run(do_cleanup())


@cleanup.command("all")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def cleanup_all(dry_run: bool, force: bool) -> None:
    """Remove all stale resources."""
    from ringmaster.cleanup import ResourceCleaner

    async def do_cleanup() -> None:
        cleaner = ResourceCleaner()
        status = await cleaner.get_status()

        total_count = (
            status["worktrees"]["count"]
            + status["branches"]["count"]
            + status["temp_files"]["count"]
            + status["scripts"]["count"]
        )

        if total_count == 0:
            console.print("[green]No resources to clean up[/green]")
            return

        total_bytes = status["worktrees"]["bytes"] + status["temp_files"]["bytes"] + status["scripts"]["bytes"]
        total_mb = total_bytes / (1024 * 1024)

        console.print(f"Found {total_count} resources ({total_mb:.1f} MB)")
        console.print(f"  - {status['worktrees']['count']} worktrees")
        console.print(f"  - {status['branches']['count']} branches")
        console.print(f"  - {status['temp_files']['count']} temp files")
        console.print(f"  - {status['scripts']['count']} scripts")

        if dry_run:
            console.print("\n[dim]Dry run - no changes made[/dim]")
            return

        if not force and not click.confirm("\nRemove all stale resources?"):
            console.print("Aborted")
            return

        stats = await cleaner.cleanup_all_stale()

        console.print("\n[green]Cleanup complete:[/green]")
        console.print(f"  - Worktrees removed: {stats.worktrees_removed}")
        console.print(f"  - Branches removed:  {stats.branches_removed}")
        console.print(f"  - Temp files removed: {stats.temp_files_removed}")
        console.print(f"  - Scripts removed:   {stats.scripts_removed}")
        if stats.bytes_freed:
            console.print(f"  - Space freed: {stats.bytes_freed / (1024 * 1024):.1f} MB")
        for error in stats.errors:
            console.print(f"  [red]Error:[/red] {error}")

    asyncio.run(do_cleanup())


@cleanup.command("task")
@click.argument("task_id")
@click.option("--worker-id", "-w", help="Worker ID for worktree cleanup")
def cleanup_task_cmd(task_id: str, worker_id: str | None) -> None:
    """Clean up resources for a specific task."""
    from ringmaster.cleanup import cleanup_task_resources

    async def do_cleanup() -> None:
        stats = await cleanup_task_resources(task_id, worker_id)

        console.print(f"[green]Cleanup for task {task_id}:[/green]")
        if stats.worktrees_removed:
            console.print(f"  - Worktree removed")
        if stats.branches_removed:
            console.print(f"  - Branch removed")
        if stats.temp_files_removed:
            console.print(f"  - {stats.temp_files_removed} temp files removed")
        if not (stats.worktrees_removed or stats.branches_removed or stats.temp_files_removed):
            console.print("  - No resources found")
        for error in stats.errors:
            console.print(f"  [red]Error:[/red] {error}")

    asyncio.run(do_cleanup())


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
