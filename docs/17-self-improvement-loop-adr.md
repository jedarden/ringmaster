# ADR-017: Self-Improvement Loop Integration

## Status

Proposed

## Context

Ringmaster has the components needed for self-improvement:

- **Workers** can modify code in git worktrees
- **HotReloader** can reload Python modules and rollback on failure
- **FileChangeWatcher** detects code changes
- **SafetyValidator** protects critical files

However, these components aren't wired together into a complete self-improvement loop. The goal is for ringmaster to:

1. Create a task to improve itself
2. Worker executes task, modifies ringmaster code
3. Changes are committed (rollback point)
4. Hot-reload the modified components
5. Health check passes → keep changes
6. Health check fails → rollback to previous commit

## Decision

### 1. Self-Improvement Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    SELF-IMPROVEMENT LOOP                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Task Created                                                │
│     └─→ "Improve enricher token estimation"                     │
│                                                                 │
│  2. Worker Claims Task                                          │
│     └─→ Works in git worktree: /ringmaster.worktrees/worker-X   │
│                                                                 │
│  3. Worker Makes Changes                                        │
│     └─→ Modifies: src/ringmaster/enricher/pipeline.py           │
│                                                                 │
│  4. Worker Commits (ROLLBACK POINT)                             │
│     └─→ git commit -m "feat(enricher): improve token estimation"│
│                                                                 │
│  5. Merge to Main                                               │
│     └─→ git merge --no-ff worker-branch                         │
│                                                                 │
│  6. Hot-Reload Triggered                                        │
│     └─→ FileChangeWatcher detects change                        │
│     └─→ HotReloader.process_changes() called                    │
│                                                                 │
│  7. Validation                                                  │
│     └─→ Run tests (pytest)                                      │
│     └─→ Run health checks                                       │
│                                                                 │
│  8a. SUCCESS                        8b. FAILURE                 │
│      └─→ importlib.reload()             └─→ git revert HEAD     │
│      └─→ Task → DONE                    └─→ Reload reverted code│
│      └─→ Cleanup worktree               └─→ Task → FAILED       │
│                                         └─→ Create follow-up    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Component Classification

Not all components can be hot-reloaded. Classification:

| Component Type | Hot-Reloadable | Reason |
|----------------|----------------|--------|
| Pure functions | Yes | No state, no side effects |
| Stateless classes | Yes | Instances can use new class definition |
| Enrichment stages | Yes | Created fresh per-request |
| Validators | Yes | Stateless |
| API routes | **No** | FastAPI caches route definitions |
| Database models | **No** | SQLAlchemy metadata cached |
| CLI commands | **No** | Click decorators cached at import |
| Worker spawner | **No** | References to spawned processes |

**Strategy for non-reloadable components:**

```python
class ComponentRegistry:
    """Tracks which components need restart vs reload."""

    REQUIRES_RESTART = {
        "ringmaster.api.routes.*",
        "ringmaster.api.app",
        "ringmaster.cli",
        "ringmaster.domain.models",
        "ringmaster.db.models",
    }

    @classmethod
    def needs_restart(cls, module_name: str) -> bool:
        return any(
            module_name.startswith(pattern.replace("*", ""))
            for pattern in cls.REQUIRES_RESTART
        )
```

### 3. Graceful Restart Protocol

When hot-reload is insufficient, perform graceful restart:

```python
async def graceful_restart(component: str):
    """Restart a component without losing state."""

    if component == "api":
        # 1. Stop accepting new requests
        await api_server.pause()

        # 2. Wait for in-flight requests to complete
        await api_server.drain(timeout=30)

        # 3. Save state to database
        await save_runtime_state()

        # 4. Restart process
        os.execv(sys.executable, [sys.executable] + sys.argv)

    elif component == "scheduler":
        # Similar drain-and-restart pattern
        pass
```

### 4. Health Checks

After reload, verify system health:

```python
class HealthChecker:
    """Post-reload health verification."""

    async def check_all(self) -> tuple[bool, list[str]]:
        """Run all health checks.

        Returns:
            Tuple of (all_passed, list of failure messages).
        """
        checks = [
            self.check_database_connection(),
            self.check_api_responsiveness(),
            self.check_worker_communication(),
            self.check_enrichment_pipeline(),
        ]

        results = await asyncio.gather(*checks, return_exceptions=True)

        failures = []
        for check, result in zip(checks, results):
            if isinstance(result, Exception):
                failures.append(f"{check.__name__}: {result}")
            elif not result:
                failures.append(f"{check.__name__}: failed")

        return len(failures) == 0, failures

    async def check_enrichment_pipeline(self) -> bool:
        """Verify enrichment pipeline works."""
        # Create a dummy task
        # Run through pipeline
        # Verify output is valid
        pass
```

### 5. Integration Points

#### Worker Completion Hook

```python
# In report-result handler
async def on_task_complete(task: Task, worker: Worker):
    # Check if task modified ringmaster code
    worktree = get_worktree(worker.id, task.id)
    modified_files = await get_modified_files(worktree)

    ringmaster_files = [
        f for f in modified_files
        if "ringmaster" in str(f)
    ]

    if ringmaster_files:
        # This is a self-improvement task
        await trigger_self_improvement_flow(task, worktree, ringmaster_files)
```

#### Self-Improvement Trigger

```python
async def trigger_self_improvement_flow(
    task: Task,
    worktree: Path,
    modified_files: list[Path],
):
    """Handle self-improvement task completion."""

    # 1. Commit changes in worktree (already done by worker)
    commit_hash = await get_latest_commit(worktree)

    # 2. Merge to main
    merge_result = await merge_worktree(worktree)
    if not merge_result.success:
        task.status = TaskStatus.FAILED
        task.failure_reason = f"Merge failed: {merge_result.error}"
        return

    # 3. Trigger hot-reload
    watcher = FileChangeWatcher([Path("src/ringmaster")])
    changes = watcher.detect_changes()

    reloader = HotReloader(
        project_root=Path.cwd(),
        safety_config=SafetyConfig(auto_rollback=True),
    )

    result = await reloader.process_changes(changes)

    # 4. Handle result
    if result.status == ReloadStatus.SUCCESS:
        # Run health checks
        health = HealthChecker()
        healthy, failures = await health.check_all()

        if healthy:
            task.status = TaskStatus.DONE
            await cleanup_worktree(worktree)
        else:
            # Revert and report
            await revert_commit(commit_hash)
            await reloader.process_changes(changes)  # Reload reverted code
            task.status = TaskStatus.FAILED
            task.failure_reason = f"Health checks failed: {failures}"

    elif result.status == ReloadStatus.ROLLED_BACK:
        task.status = TaskStatus.FAILED
        task.failure_reason = f"Tests failed, rolled back: {result.test_output}"

    else:
        task.status = TaskStatus.FAILED
        task.failure_reason = result.error_message
```

### 6. Protected Operations

Certain self-modifications require human approval:

```python
REQUIRES_HUMAN_APPROVAL = [
    # Safety system itself
    "src/ringmaster/reload/safety.py",
    "src/ringmaster/reload/reloader.py",

    # Core execution
    "src/ringmaster/worker/executor.py",

    # Database schema
    "migrations/*.sql",

    # Authentication/security
    "src/ringmaster/api/auth.py",
]
```

When a task modifies these files:
1. Task moves to REVIEW status
2. Human receives notification
3. Human approves or rejects
4. On approval, self-improvement flow continues

### 7. Rollback Strategy

Multiple rollback levels:

| Level | Trigger | Action |
|-------|---------|--------|
| 1. Module reload | Import error | `git checkout` changed files |
| 2. Test failure | Tests fail | Revert commit, reload |
| 3. Health check | System unhealthy | Revert commit, restart components |
| 4. Runtime error | Exception in reloaded code | Emergency rollback to last known good |

```python
class RollbackManager:
    """Manages rollback state and operations."""

    def __init__(self):
        self.last_known_good: str | None = None  # commit hash

    async def mark_known_good(self):
        """Mark current state as known good."""
        self.last_known_good = await get_current_commit()

    async def emergency_rollback(self):
        """Rollback to last known good state."""
        if not self.last_known_good:
            raise RuntimeError("No known good state to rollback to")

        await run_command(f"git reset --hard {self.last_known_good}")
        await restart_all_components()
```

### 8. Observability

Track self-improvement metrics:

```python
@dataclass
class SelfImprovementMetrics:
    total_attempts: int = 0
    successful_improvements: int = 0
    failed_tests: int = 0
    failed_health_checks: int = 0
    rollbacks: int = 0
    human_approvals_requested: int = 0
    human_approvals_granted: int = 0
```

## Consequences

### Positive

- Ringmaster can improve itself autonomously
- Commits provide rollback points for every change
- Hot-reload enables rapid iteration without downtime
- Safety rails prevent breaking critical components
- Health checks catch issues tests miss

### Negative

- Complexity of tracking what can/cannot be hot-reloaded
- Risk of subtle bugs from partial reloads
- Need robust health checks (chicken-and-egg: who tests the tests?)
- Graceful restart may lose some in-flight state

### Risks

- Infinite loop: improvement breaks tests, creates task to fix tests, which also breaks
- Mitigation: Circuit breaker on self-improvement tasks per component

- Cascading failures: Bad reload affects dependent modules
- Mitigation: Dependency tracking, reload in correct order

- State corruption: Reloaded class, old instances
- Mitigation: Prefer stateless components, explicit instance refresh

## Implementation Priority

1. **Wire worker completion to merge** - Get changes from worktree to main
2. **Trigger hot-reload on merge** - Connect FileChangeWatcher to repo
3. **Add health checks** - Post-reload verification
4. **Component classification** - Know what needs restart vs reload
5. **Graceful restart** - For non-reloadable components
6. **Rollback manager** - Multi-level rollback

## References

- ADR-016: Resource Cleanup
- `src/ringmaster/reload/` - Existing hot-reload implementation
- `docs/06-deployment.md` - Original deployment architecture
