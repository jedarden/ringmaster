# ADR-016: Worker Resource Cleanup

## Status

Proposed

## Context

Workers consume various resources during task execution that persist after completion:

- **Git worktrees**: Isolated working directories for parallel task execution
- **Git branches**: Task-specific branches (e.g., `ringmaster/bd-{bead_id}`)
- **Temporary files**: Prompt files, output artifacts, logs
- **Tmux sessions**: Worker process containers
- **Database records**: Completed task assignments, stale worker state

Without cleanup, these resources accumulate indefinitely. In testing, 100 worktrees consumed 828MB of disk space. Production systems running continuously would accumulate far more.

## Decision

### 1. Cleanup Responsibility Model

**Workers clean up their own resources after task completion.**

The `report-result` command (or equivalent completion signal) triggers cleanup:

```
Task Execution:
  1. pull-bead → creates worktree, branch
  2. build-prompt → creates temp files
  3. execute → runs in worktree
  4. report-result → triggers cleanup
       └── removes worktree
       └── deletes task branch
       └── removes temp files
```

### 2. Resource Types and Cleanup Strategy

#### Git Worktrees

| Trigger | Action |
|---------|--------|
| Task completion (success) | Remove worktree immediately |
| Task failure (will retry) | Keep worktree for debugging |
| Task failure (max retries) | Remove after configurable delay (default: 1 hour) |
| Worker shutdown | Remove all worktrees for that worker |

```python
# In report_result handler
if success or attempts >= max_attempts:
    await cleanup_worktree(task_id, worker_id)
```

#### Git Branches

Task branches follow the same lifecycle as worktrees:

```bash
# Cleanup after task completion
git worktree remove /path/to/worktree
git branch -D ringmaster/bd-{bead_id}
```

#### Temporary Files

| File Type | Location | Cleanup |
|-----------|----------|---------|
| Prompt files | `/tmp/ringmaster-prompt-{id}.txt` | After task execution |
| Output files | `/tmp/ringmaster-output-{id}.*` | After result reported |
| Worker scripts | `/tmp/ringmaster-workers/` | On worker shutdown |

#### Tmux Sessions

| Event | Action |
|-------|--------|
| Worker marked offline | Kill tmux session |
| Stale session detected | Kill if no heartbeat for 5 minutes |
| System startup | Clean orphaned `rm-worker-*` sessions |

### 3. Periodic Cleanup Job

A background cleanup job runs independently to catch missed cleanups:

```python
class ResourceCleaner:
    """Periodic cleanup of stale resources."""

    async def run(self, interval: int = 3600):  # hourly
        while True:
            await self.cleanup_stale_worktrees()
            await self.cleanup_orphan_branches()
            await self.cleanup_temp_files()
            await self.cleanup_dead_sessions()
            await asyncio.sleep(interval)

    async def cleanup_stale_worktrees(self):
        """Remove worktrees for completed/failed tasks."""
        # Find worktrees older than retention period
        # Cross-reference with task status
        # Remove if task is done/failed

    async def cleanup_orphan_branches(self):
        """Remove branches with no associated worktree or task."""
        # List ringmaster/bd-* branches
        # Check if task exists and is active
        # Delete if orphaned
```

### 4. Configuration

```yaml
# ringmaster.yaml
cleanup:
  # Immediate cleanup on task completion
  on_completion: true

  # Retention for failed tasks (for debugging)
  failed_task_retention: 3600  # seconds

  # Periodic cleanup interval
  periodic_interval: 3600  # seconds

  # Resource-specific settings
  worktrees:
    max_age: 86400  # 24 hours
    max_count: 50   # per project

  temp_files:
    max_age: 3600   # 1 hour

  branches:
    cleanup_on_task_done: true
    preserve_merged: false
```

### 5. CLI Commands

```bash
# Manual cleanup commands
ringmaster cleanup worktrees [--dry-run] [--force]
ringmaster cleanup branches [--dry-run] [--pattern "ringmaster/bd-*"]
ringmaster cleanup temp [--dry-run]
ringmaster cleanup all [--dry-run]

# Status/reporting
ringmaster cleanup status
# Output:
#   Worktrees: 15 (127MB)
#   Orphan branches: 3
#   Temp files: 45 (12MB)
#   Stale sessions: 2

# Existing command enhanced
ringmaster worker prune-worktrees [--all-projects]
```

### 6. Implementation Phases

#### Phase 1: Immediate Cleanup (MVP)

Add cleanup to `report-result`:

```python
@cli.command("report-result")
async def report_result(task_id: str, status: str, ...):
    # ... existing result handling ...

    # Cleanup resources
    if status == "completed" or task.attempts >= task.max_attempts:
        await cleanup_task_resources(task_id, task.worker_id)

async def cleanup_task_resources(task_id: str, worker_id: str):
    """Clean up resources associated with a completed task."""
    worktree_path = get_worktree_path(worker_id, task_id)
    branch_name = f"ringmaster/bd-{task_id}"

    # Remove worktree
    if worktree_path and worktree_path.exists():
        await run_command(f"git worktree remove {worktree_path}")

    # Delete branch
    await run_command(f"git branch -D {branch_name}")

    # Remove temp files
    for pattern in [f"/tmp/ringmaster-prompt-{task_id}*",
                    f"/tmp/ringmaster-output-{task_id}*"]:
        for f in glob.glob(pattern):
            os.unlink(f)
```

#### Phase 2: Periodic Cleanup

Add scheduler job for catching missed cleanups.

#### Phase 3: Resource Tracking

Track resource creation/cleanup in database for auditing:

```sql
CREATE TABLE resource_tracking (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,  -- worktree, branch, temp_file, session
    resource_path TEXT NOT NULL,
    task_id TEXT,
    worker_id TEXT,
    created_at TEXT NOT NULL,
    cleaned_at TEXT,
    cleanup_reason TEXT  -- completed, failed, expired, manual
);
```

## Consequences

### Positive

- Disk space remains bounded
- No manual cleanup required
- Failed task resources preserved for debugging (configurable)
- Audit trail of resource lifecycle

### Negative

- Slight overhead on task completion
- Need to handle cleanup failures gracefully
- Debugging harder if resources cleaned too eagerly

### Risks

- Race conditions if multiple processes try to clean same resource
- Orphaned resources if worker crashes before cleanup
- Branch deletion could fail if changes not merged

## Alternatives Considered

### 1. Central Cleanup Service

A dedicated service monitors and cleans all resources.

**Rejected**: Adds operational complexity. Worker self-cleanup is simpler.

### 2. No Worktrees (Single Working Directory)

Workers share a single working directory with git stash/checkout.

**Rejected**: Prevents parallel task execution on same project.

### 3. Container-per-Task

Each task runs in a disposable container.

**Rejected**: Higher overhead, more complex orchestration. May revisit for cloud deployment.

## References

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- ADR-002: Worker Interface (worktree creation)
- ADR-014: MVP Bootstrap (resource considerations)
