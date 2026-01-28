# Ringmaster Marathon 2: Self-Hosting Bootstrap Progress

## Current State

**Status**: CLI DATABASE CONNECTION FIX - READY FOR WORKER TESTING
**Iteration**: 4

**Goal**: Get Ringmaster sophisticated enough to continue improving itself.

## Self-Hosting Capability Checklist

| Capability | Status | Notes |
|------------|--------|-------|
| API Server Stability | ✅ Running | http://localhost:8080/health returns healthy |
| Database Initialized | ✅ Complete | ~/.ringmaster/ringmaster.db with all migrations |
| Worker Spawning | ✅ Validated | spawner.py fixed, CLI commands work |
| Task Creation | ✅ Working | API POST /api/tasks works, PATCH status works |
| Worker Lifecycle | ✅ Working | pull-bead, build-prompt, report-result all validated |
| Output Parsing | ⚠️ Code exists | outcome.py exists, need real worker test |
| Hot-Reload | ✅ Validated | File watcher, test runner, module reload, rollback all work |
| Self-Project Setup | ✅ Done | "Ringmaster" project created (c892ec79...) |
| Bootstrap Sequence | ✅ Script exists | scripts/bootstrap-selfhost.sh |
| Self-Improvement Loop | ⚠️ Blocked | Worker script needs testing with fixed CLI |

## Iteration 4 Accomplishments

### Fixed CLI Database Connection Hang

The worker CLI commands (`pull-bead`, `build-prompt`, `report-result`, `worker spawn`) were hanging after execution due to aiosqlite's background thread not being cleaned up properly.

**Root Cause**: `asyncio.run()` wasn't closing the database connection, causing the program to hang waiting for aiosqlite's background thread.

**Fix**: Added `run_async()` helper function that ensures `close_database()` is called after every async CLI command:

```python
def run_async(coro: Callable[[], Awaitable[T]]) -> T:
    """Run an async function with proper database cleanup."""
    from ringmaster.db import close_database

    async def wrapped() -> T:
        try:
            return await coro()
        finally:
            await close_database()

    return asyncio.run(wrapped())
```

**Files Modified**:
- `src/ringmaster/cli.py` - Added `run_async()` helper, updated 4 commands
- `src/ringmaster/db/__init__.py` - Exported `close_database`

### Validated CLI Commands Now Work

All critical worker CLI commands now complete properly:

1. **pull-bead** ✅
   ```
   $ ringmaster pull-bead worker-0bc3a778 --json
   {"id": "bd-b369e265", "title": "Test CLI fix", ...}
   Database connection closed
   ```

2. **build-prompt** ✅
   ```
   $ ringmaster build-prompt bd-b369e265 -d /home/coder/ringmaster
   Found 5 relevant files (~11996 tokens)
   # System Prompt...
   Database connection closed
   ```

3. **report-result** ✅
   ```
   $ ringmaster report-result bd-b369e265 --status completed
   Task bd-b369e265 marked as completed
   Worker selfhost-worker returned to idle
   Database connection closed
   ```

### Tests Pass
- 718 tests passed, 13 skipped
- No regressions introduced by the fix

## Previous Iterations

### Iteration 3: Hot-Reload Validation ✅
- File change detection works
- Test runner executes properly
- Module reloading works
- Rollback on test failure works
- API server stays up during reload

### Iteration 2: Core Flow Validation ✅
- Fixed spawner script CLI arguments
- Validated task creation/update APIs
- Tested worker lifecycle management

## Next Steps

### IMMEDIATE: Test Real Worker Flow
With CLI now working, the next step is to test the full self-improvement loop:

1. **Start fresh worker in tmux**:
   ```bash
   # Kill any old sessions
   tmux kill-session -t rm-worker-worker-0bc3a778 2>/dev/null || true

   # Spawn new worker
   ringmaster worker spawn worker-0bc3a778 -w /home/coder/ringmaster
   ```

2. **Create real self-improvement task**:
   ```bash
   curl -X POST http://localhost:8080/api/tasks \
     -H "Content-Type: application/json" \
     -d '{"project_id": "c892ec79-2eb9-4641-9e0b-c62e087771d5", "title": "Add version to hot-reload log", "priority": "P2"}'

   curl -X PATCH http://localhost:8080/api/tasks/TASK_ID \
     -H "Content-Type: application/json" \
     -d '{"status": "ready"}'
   ```

3. **Watch worker pick up task and execute**:
   ```bash
   tmux attach-session -t rm-worker-worker-0bc3a778
   ```

4. **Verify hot-reload triggers** after worker modifies code

### Phase 2: Self-Hosting Complete
Once the above flow works end-to-end:
- Worker pulls task
- Worker builds prompt
- Worker executes Claude Code
- Worker reports result
- Hot-reload detects changes
- Tests run automatically
- Modules reload on success

Then we can output: `<promise>SELF-HOSTING-CAPABLE</promise>`

## Blocking Issues

**CLI now works** - main blocker removed.

Remaining validation needed:
1. Test worker script actually runs the full loop
2. Verify Claude Code execution works in worker
3. Confirm hot-reload triggers after worker completion

## Commands for Testing

```bash
# Start API server (if needed)
cd /home/coder/ringmaster && nohup python3 -m ringmaster.cli serve --host 0.0.0.0 --port 8080 > /tmp/ringmaster-api.log 2>&1 &

# Check health
curl http://localhost:8080/health

# Create task
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"project_id": "c892ec79-2eb9-4641-9e0b-c62e087771d5", "title": "Test task", "priority": "P2"}'

# Mark ready
curl -X PATCH http://localhost:8080/api/tasks/TASK_ID \
  -H "Content-Type: application/json" \
  -d '{"status": "ready"}'

# Worker commands (now work without hanging!)
ringmaster pull-bead worker-0bc3a778 --json
ringmaster build-prompt TASK_ID -d /home/coder/ringmaster
ringmaster report-result TASK_ID --status completed

# Spawn worker
ringmaster worker spawn worker-0bc3a778 -w /home/coder/ringmaster
```
