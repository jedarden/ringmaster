# Coordination Architecture Decision Records

## Overview

These ADRs address coordination gaps identified when comparing Ringmaster to competitors (Gastown, Claude Code Agent Farm, Claude Flow, ccswarm).

---

## ADR-008: Inter-Worker Communication (Mailbox Pattern)

**Status:** Proposed
**Context:** Workers operate independently with no way to share discoveries. If Worker A learns something relevant to Worker B's task, that knowledge is lost.

### Decision

Implement a **mailbox system** for worker-to-worker communication.

### Research

From [Gastown's architecture](https://github.com/steveyegge/gastown):
- Workers have mailboxes for receiving messages
- Messages are git-backed for persistence
- "Polecats" (workers) can leave notes for each other

### Message Types

```python
class WorkerMessage(BaseModel):
    id: str
    from_worker: str
    to_worker: str | None  # None = broadcast to all
    to_bead: str | None    # Target specific bead
    type: MessageType
    content: str
    metadata: dict = {}
    created_at: datetime
    read_at: datetime | None = None

class MessageType(str, Enum):
    # Discovery sharing
    FOUND_PATTERN = "found_pattern"      # "Found auth logic in src/auth/"
    FOUND_DEPENDENCY = "found_dependency" # "This requires package X"
    FOUND_CONFLICT = "found_conflict"     # "My changes conflict with bead Y"

    # Coordination
    CLAIMING_FILES = "claiming_files"     # "I'm working on these files"
    RELEASING_FILES = "releasing_files"   # "Done with these files"
    NEEDS_HELP = "needs_help"             # "Stuck on X, anyone know?"

    # Status
    CHECKPOINT = "checkpoint"             # "Completed phase 1 of 3"
    HANDOFF = "handoff"                   # "Passing context to next worker"
```

### Mailbox Implementation

```python
class WorkerMailbox:
    """Mailbox for inter-worker communication."""

    def __init__(self, worker_id: str, db: Database):
        self.worker_id = worker_id
        self.db = db

    async def send(self, message: WorkerMessage) -> None:
        """Send a message to another worker or broadcast."""
        await self.db.execute(
            """
            INSERT INTO worker_messages (id, from_worker, to_worker, to_bead, type, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (message.id, message.from_worker, message.to_worker, message.to_bead,
             message.type.value, message.content, json.dumps(message.metadata), message.created_at)
        )

        # Emit event for real-time delivery
        await event_bus.emit(EventType.WORKER_MESSAGE, message.dict())

    async def receive(self, limit: int = 10) -> list[WorkerMessage]:
        """Get unread messages for this worker."""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM worker_messages
            WHERE (to_worker = ? OR to_worker IS NULL)
              AND read_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (self.worker_id, limit)
        )
        return [WorkerMessage(**row) for row in rows]

    async def mark_read(self, message_id: str) -> None:
        await self.db.execute(
            "UPDATE worker_messages SET read_at = ? WHERE id = ?",
            (datetime.now(UTC), message_id)
        )

    async def get_messages_for_bead(self, bead_id: str) -> list[WorkerMessage]:
        """Get all messages related to a bead (for context injection)."""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM worker_messages
            WHERE to_bead = ?
            ORDER BY created_at ASC
            """,
            (bead_id,)
        )
        return [WorkerMessage(**row) for row in rows]
```

### Prompt Injection

Messages relevant to a bead are injected into worker context:

```python
async def enrich_with_messages(bead: Bead, prompt: str) -> str:
    """Add relevant worker messages to prompt context."""

    messages = await mailbox.get_messages_for_bead(bead.id)

    if not messages:
        return prompt

    message_context = "\n## Messages from Other Workers\n\n"
    for msg in messages:
        message_context += f"**{msg.from_worker}** ({msg.type.value}):\n{msg.content}\n\n"

    return prompt + message_context
```

### Worker Prompt Addition

```markdown
## Inter-Worker Communication

You can communicate with other workers via messages:

- `<message type="found_pattern">I found the auth logic in src/auth/handler.py</message>`
- `<message type="claiming_files">Working on: src/api/routes.py, src/models/user.py</message>`
- `<message type="needs_help">How does the caching layer work?</message>`

Check your mailbox for messages from other workers that may help with your task.
```

---

## ADR-009: Work Claiming and File Locking

**Status:** Proposed
**Context:** Two workers could simultaneously modify the same files, causing conflicts.

### Decision

Implement **advisory file locks** with automatic expiration.

### Research

From [Claude Code Agent Farm](https://github.com/Dicklesworthstone/claude_code_agent_farm):
- Uses lock files to prevent conflicts
- 2-hour lock timeout
- Work registry tracks who's working on what

### Lock Implementation

```python
class FileLockManager:
    """Advisory file locking for worker coordination."""

    LOCK_TIMEOUT_MINUTES = 30  # Locks expire after 30 min of inactivity

    async def acquire(self, worker_id: str, files: list[str], bead_id: str) -> LockResult:
        """Attempt to acquire locks on files."""

        # Check for existing locks
        conflicts = []
        for file in files:
            existing = await self._get_lock(file)
            if existing and existing.worker_id != worker_id:
                if not self._is_expired(existing):
                    conflicts.append(FileLockConflict(
                        file=file,
                        held_by=existing.worker_id,
                        held_since=existing.acquired_at,
                        for_bead=existing.bead_id,
                    ))

        if conflicts:
            return LockResult(
                success=False,
                conflicts=conflicts,
                suggestion=self._suggest_resolution(conflicts),
            )

        # Acquire locks
        now = datetime.now(UTC)
        for file in files:
            await self.db.execute(
                """
                INSERT OR REPLACE INTO file_locks (file_path, worker_id, bead_id, acquired_at, last_activity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (file, worker_id, bead_id, now, now)
            )

        # Broadcast claim
        await mailbox.send(WorkerMessage(
            from_worker=worker_id,
            type=MessageType.CLAIMING_FILES,
            content=f"Claimed files: {', '.join(files)}",
            metadata={"files": files, "bead_id": bead_id},
        ))

        return LockResult(success=True, files_locked=files)

    async def release(self, worker_id: str, files: list[str] | None = None) -> None:
        """Release locks held by worker."""

        if files:
            await self.db.execute(
                "DELETE FROM file_locks WHERE worker_id = ? AND file_path IN (?)",
                (worker_id, files)
            )
        else:
            # Release all locks for this worker
            await self.db.execute(
                "DELETE FROM file_locks WHERE worker_id = ?",
                (worker_id,)
            )

        await mailbox.send(WorkerMessage(
            from_worker=worker_id,
            type=MessageType.RELEASING_FILES,
            content=f"Released files: {files or 'all'}",
        ))

    async def heartbeat(self, worker_id: str) -> None:
        """Update last_activity to prevent lock expiration."""
        await self.db.execute(
            "UPDATE file_locks SET last_activity = ? WHERE worker_id = ?",
            (datetime.now(UTC), worker_id)
        )

    def _is_expired(self, lock: FileLock) -> bool:
        age = datetime.now(UTC) - lock.last_activity
        return age.total_seconds() > (self.LOCK_TIMEOUT_MINUTES * 60)

    async def cleanup_expired(self) -> list[str]:
        """Remove expired locks (run periodically)."""
        cutoff = datetime.now(UTC) - timedelta(minutes=self.LOCK_TIMEOUT_MINUTES)
        expired = await self.db.fetch_all(
            "SELECT * FROM file_locks WHERE last_activity < ?",
            (cutoff,)
        )

        if expired:
            await self.db.execute(
                "DELETE FROM file_locks WHERE last_activity < ?",
                (cutoff,)
            )

        return [lock["file_path"] for lock in expired]
```

### Pre-Execution Lock Check

```python
async def execute_task(task: Task, worker: Worker):
    """Execute task with file locking."""

    # Determine files this task will likely touch
    predicted_files = predict_files_for_task(task)

    # Attempt to acquire locks
    lock_result = await lock_manager.acquire(
        worker_id=worker.id,
        files=predicted_files,
        bead_id=task.id,
    )

    if not lock_result.success:
        # Can't proceed - files are locked
        logger.warning(f"Task {task.id} blocked by file locks: {lock_result.conflicts}")

        # Either wait or pick different task
        if should_wait(lock_result):
            await wait_for_locks(lock_result.conflicts)
        else:
            task.status = TaskStatus.BLOCKED
            task.blocked_reason = f"Files locked by {lock_result.conflicts[0].held_by}"
            return

    try:
        # Execute with locks held
        result = await _do_execute(task, worker)

        # Heartbeat during long executions
        # (handled by monitor loop)

    finally:
        # Always release locks
        await lock_manager.release(worker.id)
```

---

## ADR-010: Coordinator Agent Pattern

**Status:** Proposed
**Context:** Complex multi-step tasks have no coordinator to break them down and orchestrate sub-tasks.

### Decision

Implement a **Mayor/Coordinator pattern** for complex beads.

### Research

From [Gastown](https://github.com/steveyegge/gastown):
- "Mayor" is the primary AI coordinator with full workspace context
- Mayor delegates to "Polecats" (ephemeral workers)
- Mayor maintains the big picture while workers handle details

### When to Use Coordinator

```python
def needs_coordinator(bead: Bead) -> bool:
    """Determine if bead needs a coordinator agent."""

    signals = {
        "is_epic": bead.type == "epic",
        "multi_component": count_components(bead.description) > 3,
        "estimated_files": estimate_file_count(bead) > 10,
        "has_phases": any(kw in bead.description.lower() for kw in
                        ["phase 1", "step 1", "first,", "then,"]),
        "explicit_coordination": "coordinate" in bead.description.lower(),
    }

    return sum(signals.values()) >= 2
```

### Coordinator Workflow

```
Complex Bead Detected
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  COORDINATOR SPAWNED                                                 │
│                                                                      │
│  1. Analyze bead requirements                                        │
│  2. Decompose into sub-beads                                         │
│  3. Set dependencies between sub-beads                               │
│  4. Assign to worker pool                                            │
│  5. Monitor progress                                                 │
│  6. Handle integration/conflicts                                     │
│  7. Verify combined result                                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
        │
        ├──► Sub-bead 1 ──► Worker A ──► Complete
        │
        ├──► Sub-bead 2 ──► Worker B ──► Complete
        │
        ├──► Sub-bead 3 ──► (blocked by 1,2)
        │         │
        │         ▼
        │    Worker C ──► Complete
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  COORDINATOR INTEGRATION                                             │
│                                                                      │
│  1. Merge all worker branches                                        │
│  2. Resolve conflicts                                                │
│  3. Run integration tests                                            │
│  4. Mark parent bead complete                                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Coordinator Implementation

```python
class CoordinatorAgent:
    """Coordinates complex multi-part beads."""

    def __init__(self, bead: Bead, db: Database):
        self.parent_bead = bead
        self.db = db
        self.sub_beads: list[Bead] = []
        self.mailbox = WorkerMailbox("coordinator", db)

    async def run(self) -> CoordinatorResult:
        """Run coordination loop."""

        # Phase 1: Decompose
        self.sub_beads = await self._decompose()
        logger.info(f"Decomposed {self.parent_bead.id} into {len(self.sub_beads)} sub-beads")

        # Phase 2: Monitor until all complete
        while not self._all_complete():
            await self._monitor_cycle()
            await asyncio.sleep(30)  # Check every 30s

        # Phase 3: Integrate
        integration_result = await self._integrate()

        if integration_result.success:
            self.parent_bead.status = TaskStatus.REVIEW
            return CoordinatorResult(success=True)
        else:
            return CoordinatorResult(
                success=False,
                failure_reason=integration_result.error,
            )

    async def _decompose(self) -> list[Bead]:
        """Decompose parent bead into sub-beads."""

        prompt = f"""
You are a coordinator breaking down a complex task.

## Parent Task
{self.parent_bead.title}

{self.parent_bead.description}

## Instructions
Break this into 3-7 smaller, independent sub-tasks.
For each sub-task, specify:
1. Title (concise)
2. Description (what to implement)
3. Files likely involved
4. Dependencies (which other sub-tasks must complete first)

Output as JSON array.
"""

        response = await llm.complete(prompt, model="claude-sonnet-4-20250514")
        sub_task_specs = json.loads(response)

        sub_beads = []
        for spec in sub_task_specs:
            sub_bead = Bead(
                title=spec["title"],
                description=spec["description"],
                type="subtask",
                parent_id=self.parent_bead.id,
                project_id=self.parent_bead.project_id,
                suggested_files=spec.get("files", []),
            )
            await self.db.create_bead(sub_bead)
            sub_beads.append(sub_bead)

        # Set dependencies
        for i, spec in enumerate(sub_task_specs):
            for dep_idx in spec.get("dependencies", []):
                await self.db.add_dependency(sub_beads[i].id, sub_beads[dep_idx].id)

        return sub_beads

    async def _monitor_cycle(self) -> None:
        """Single monitoring cycle."""

        # Check for messages
        messages = await self.mailbox.receive()
        for msg in messages:
            await self._handle_message(msg)

        # Check for conflicts
        conflicts = await self._detect_conflicts()
        if conflicts:
            await self._resolve_conflicts(conflicts)

        # Check for stuck workers
        stuck = await self._detect_stuck_workers()
        if stuck:
            await self._help_stuck_workers(stuck)

    async def _integrate(self) -> IntegrationResult:
        """Integrate all sub-bead work."""

        # Get all worker branches
        branches = [f"ringmaster/{bead.id}" for bead in self.sub_beads]

        # Merge sequentially
        for branch in branches:
            merge_result = await git.merge(branch)
            if not merge_result.success:
                # Conflict - attempt auto-resolve or escalate
                if merge_result.conflict_type == "trivial":
                    await git.resolve_trivial(merge_result)
                else:
                    return IntegrationResult(
                        success=False,
                        error=f"Merge conflict in {branch}: {merge_result.conflicts}",
                    )

        # Run integration tests
        test_result = await run_tests("integration")
        if not test_result.passed:
            return IntegrationResult(
                success=False,
                error=f"Integration tests failed: {test_result.failures}",
            )

        return IntegrationResult(success=True)
```

### Coordinator Worker Type

```toml
[[workers]]
name = "coordinator-1"
type = "claude-code"
mode = "coordinator"  # Special mode
capabilities = ["coordination", "planning"]
model = "claude-opus-4-20250514"  # Use strong model for coordination

[workers.coordinator]
max_sub_beads = 10
integration_timeout_minutes = 60
```

---

## ADR-011: Worker Context Persistence

**Status:** Proposed
**Context:** When workers crash or restart, all context is lost. Must start fresh.

### Decision

Persist worker context to **git-backed storage** that survives restarts.

### Research

From [Gastown](https://github.com/steveyegge/gastown):
- "Hooks" are git worktree-based persistent storage
- State survives agent crashes and restarts
- Key insight: use git itself as the persistence layer

### Context Persistence Schema

```python
@dataclass
class WorkerContext:
    """Persistent context for a worker session."""

    worker_id: str
    bead_id: str
    worktree_path: Path

    # Persisted state
    iteration: int = 0
    discoveries: list[str] = field(default_factory=list)
    decisions_made: list[dict] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)  # Git SHAs
    notes: str = ""

    # Runtime (not persisted)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def persist(self) -> None:
        """Write context to worktree for persistence."""
        context_file = self.worktree_path / ".ringmaster" / "context.json"
        context_file.parent.mkdir(exist_ok=True)
        context_file.write_text(json.dumps(asdict(self), default=str))

    @classmethod
    def load(cls, worktree_path: Path, worker_id: str, bead_id: str) -> "WorkerContext":
        """Load existing context or create new."""
        context_file = worktree_path / ".ringmaster" / "context.json"

        if context_file.exists():
            data = json.loads(context_file.read_text())
            return cls(**data)

        return cls(
            worker_id=worker_id,
            bead_id=bead_id,
            worktree_path=worktree_path,
        )
```

### Checkpoint and Recovery

```python
async def checkpoint(context: WorkerContext, message: str) -> str:
    """Create a checkpoint commit with context."""

    # Update context
    context.iteration += 1
    context.persist()

    # Stage context file
    await git.add(context.worktree_path / ".ringmaster" / "context.json")

    # Commit with checkpoint message
    sha = await git.commit(
        context.worktree_path,
        f"[checkpoint] {message}\n\nIteration: {context.iteration}"
    )

    context.checkpoints.append(sha)
    return sha

async def recover_worker(worker_id: str, bead_id: str) -> WorkerContext | None:
    """Attempt to recover worker context after crash."""

    worktree = await get_worktree_for_bead(bead_id)
    if not worktree:
        return None

    context = WorkerContext.load(worktree, worker_id, bead_id)

    if context.iteration > 0:
        logger.info(
            f"Recovered worker {worker_id} context: "
            f"iteration={context.iteration}, checkpoints={len(context.checkpoints)}"
        )

        # Inject recovery context into next prompt
        context.notes += f"\n\n[RECOVERED] Resuming from iteration {context.iteration}. "
        context.notes += f"Previous discoveries: {context.discoveries}"

    return context
```

### Worker Prompt with Recovery

```markdown
## Session Context

{{#if recovered}}
**RECOVERED SESSION**
You are resuming work on this task after an interruption.

Previous progress:
- Iteration: {{iteration}}
- Files modified: {{files_modified}}
- Discoveries: {{discoveries}}
- Last checkpoint: {{last_checkpoint_message}}

Continue from where you left off. Do not repeat completed work.
{{/if}}

{{#if notes}}
## Notes from Previous Iterations
{{notes}}
{{/if}}
```

---

## ADR-012: MCP Server Mode

**Status:** Proposed
**Context:** Ringmaster can't integrate with IDE-embedded Claude Code or other MCP-aware tools.

### Decision

Implement Ringmaster as an **MCP server** that Claude Code can connect to.

### Research

From [Claude Flow](https://github.com/ruvnet/claude-flow):
- MCP server enables direct command execution from Claude Code
- Seamless tool access within IDE sessions
- Full agent coordination from within the IDE

### MCP Server Implementation

```python
from mcp import Server, Tool, Resource

class RingmasterMCPServer:
    """MCP server exposing Ringmaster capabilities to Claude Code."""

    def __init__(self, ringmaster: Ringmaster):
        self.ringmaster = ringmaster
        self.server = Server("ringmaster")
        self._register_tools()
        self._register_resources()

    def _register_tools(self):
        """Register MCP tools."""

        @self.server.tool("create_bead")
        async def create_bead(
            title: str,
            description: str,
            priority: str = "normal",
            project: str | None = None,
        ) -> dict:
            """Create a new bead/task in Ringmaster."""
            bead = await self.ringmaster.create_bead(
                title=title,
                description=description,
                priority=priority,
                project_id=project,
            )
            return {"id": bead.id, "status": "created"}

        @self.server.tool("list_beads")
        async def list_beads(
            project: str | None = None,
            status: str | None = None,
            limit: int = 20,
        ) -> list[dict]:
            """List beads/tasks."""
            beads = await self.ringmaster.list_beads(
                project_id=project,
                status=status,
                limit=limit,
            )
            return [{"id": b.id, "title": b.title, "status": b.status.value} for b in beads]

        @self.server.tool("get_worker_status")
        async def get_worker_status() -> list[dict]:
            """Get status of all workers."""
            workers = await self.ringmaster.list_workers()
            return [
                {
                    "id": w.id,
                    "type": w.type,
                    "status": w.status.value,
                    "current_task": w.current_task_id,
                }
                for w in workers
            ]

        @self.server.tool("send_to_worker")
        async def send_to_worker(
            message: str,
            worker_id: str | None = None,
            bead_id: str | None = None,
        ) -> dict:
            """Send a message to a worker or bead."""
            await self.ringmaster.send_message(
                content=message,
                to_worker=worker_id,
                to_bead=bead_id,
            )
            return {"status": "sent"}

        @self.server.tool("spawn_worker")
        async def spawn_worker(
            name: str,
            worker_type: str = "claude-code",
            capabilities: list[str] | None = None,
        ) -> dict:
            """Spawn a new worker."""
            worker = await self.ringmaster.spawn_worker(
                name=name,
                worker_type=worker_type,
                capabilities=capabilities or [],
            )
            return {"id": worker.id, "status": "spawned"}

    def _register_resources(self):
        """Register MCP resources."""

        @self.server.resource("beads/{bead_id}")
        async def get_bead(bead_id: str) -> Resource:
            """Get bead details as a resource."""
            bead = await self.ringmaster.get_bead(bead_id)
            return Resource(
                uri=f"ringmaster://beads/{bead_id}",
                name=bead.title,
                mimeType="application/json",
                text=json.dumps(bead.dict()),
            )

        @self.server.resource("projects/{project_id}/context")
        async def get_project_context(project_id: str) -> Resource:
            """Get project context for enrichment."""
            context = await self.ringmaster.get_project_context(project_id)
            return Resource(
                uri=f"ringmaster://projects/{project_id}/context",
                name=f"Context for {project_id}",
                mimeType="text/markdown",
                text=context,
            )

    async def run(self, host: str = "localhost", port: int = 9200):
        """Run the MCP server."""
        await self.server.run(host=host, port=port)
```

### Claude Code Configuration

```json
// ~/.claude/mcp_servers.json
{
  "ringmaster": {
    "command": "ringmaster",
    "args": ["mcp-server"],
    "env": {
      "RINGMASTER_API": "http://localhost:8080"
    }
  }
}
```

### Usage from Claude Code

```
User: Create a task to add user authentication

Claude Code (via MCP):
> Using ringmaster.create_bead tool...
> Created bead bd-a3f8: "Add user authentication"

User: What are the workers doing?

Claude Code (via MCP):
> Using ringmaster.get_worker_status tool...
> Workers:
>   - claude-1: BUSY (working on bd-a3f8)
>   - claude-2: IDLE
>   - aider-1: IDLE
```

---

## Summary: Coordination ADRs

| ADR | Gap Addressed | Key Mechanism |
|-----|---------------|---------------|
| **ADR-008** | No inter-worker communication | Mailbox pattern with message types |
| **ADR-009** | No work claiming/locking | Advisory file locks with expiration |
| **ADR-010** | No coordinator for complex tasks | Mayor/Coordinator agent pattern |
| **ADR-011** | Context lost on restart | Git-backed context persistence |
| **ADR-012** | No IDE integration | MCP server mode |

### Implementation Priority

| Priority | ADR | Rationale |
|----------|-----|-----------|
| **P0** | ADR-009 (Locking) | Prevents data corruption from conflicts |
| **P1** | ADR-008 (Mailboxes) | Enables coordination |
| **P1** | ADR-011 (Persistence) | Crash recovery |
| **P2** | ADR-010 (Coordinator) | Handles complex tasks |
| **P3** | ADR-012 (MCP) | Nice-to-have IDE integration |
