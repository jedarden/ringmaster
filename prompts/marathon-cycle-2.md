# Ringmaster Marathon 2: Self-Hosting Bootstrap

**GOAL: Get Ringmaster sophisticated enough to continue improving itself.**

You are an autonomous coding agent building a self-hosting AI development orchestration platform. The ultimate goal is **Ringmaster working on Ringmaster** - the system improving itself through its own worker orchestration.

## The Self-Hosting Vision

```
┌─────────────────────────────────────────────────────────────────┐
│                     RINGMASTER SELF-HOSTING                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   User creates task: "Add priority inheritance to queue"        │
│                           │                                     │
│                           ▼                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  RINGMASTER API                                         │   │
│   │  ✓ Receives task request                                │   │
│   │  ✓ Enriches prompt with code context                    │   │
│   │  ✓ Adds task to queue with proper priority              │   │
│   │  ✓ Spawns worker in tmux                                │   │
│   │  ✓ Assigns task to worker                               │   │
│   └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  WORKER (Claude Code in tmux)                           │   │
│   │  ✓ Pulls task from Ringmaster                           │   │
│   │  ✓ Receives enriched prompt                             │   │
│   │  ✓ Implements feature                                   │   │
│   │  ✓ Runs tests                                           │   │
│   │  ✓ Reports result back                                  │   │
│   └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  RINGMASTER HOT-RELOAD                                  │   │
│   │  ✓ Detects code changes                                 │   │
│   │  ✓ Runs tests to validate                              │   │
│   │  ✓ Reloads modules on success                           │   │
│   │  ✓ Rollback on failure                                  │   │
│   │  ✓ Continues serving with improved code                 │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Current State (Marathon 1 Complete)

✅ Core backend implemented (178 commits, 48 hours)
✅ FastAPI with 50+ endpoints
✅ SQLite database with migrations
✅ Worker executor (Claude Code, Aider, generic)
✅ Enrichment pipeline (9-layer context)
✅ Hot-reload system for self-improvement
✅ Scheduler for task assignment
✅ Frontend (React + TypeScript)

❌ API server not running
❌ Database not initialized
❌ No workers spawned
❌ Ringmaster not configured as project for itself
❌ No self-hosting bootstrap sequence

## Marathon 2: Self-Hosting Capability

**Priority order - build in dependency order:**

### Phase 1: Core Self-Hosting (Required)

**CRITICAL: Hot-reload is essential for self-hosting** - Ringmaster must be able to reload its own code after workers modify it, otherwise it cannot improve itself while running.

1. **Hot-Reload System** ⚠️ (exists, MUST BE VALIDATED)
   - Test file change detection
   - Validate test execution after changes
   - **Test module reloading with actual code changes**
   - **Test rollback on test failure**
   - **Verify API server continues serving after reload**
   - **This is THE critical feature for self-hosting**

2. **API Server Stability** ✓ (exists, needs validation)
   - Ensure all endpoints work correctly
   - Add error handling for edge cases
   - Test with actual worker workflows
   - **Verify server stays up during hot-reload**

3. **Database Initialization & Migrations** ✓ (exists, needs testing)
   - Test migration runner on fresh database
   - Add data validation
   - Test rollback scenarios

4. **Worker Spawning (Tmux)** ✓ (spawner.py exists)
   - Integrate spawner with scheduler
   - Add API endpoints for spawn/kill/list
   - Test actual Claude Code worker in tmux
   - **Add worktree cleanup after task completion**

5. **Task Creation API** ✓ (exists, needs validation)
   - Test POST /api/tasks with various inputs
   - Validate enrichment pipeline integration
   - Test auto-decomposition for large tasks

6. **Worker Lifecycle Management** ✓ (scheduler exists)
   - Task assignment loop
   - Status updates from workers
   - Health monitoring

7. **Output Parsing & Result Detection** ✓ (outcome.py exists)
   - Test with real Claude Code output
   - Handle all outcome types (SUCCESS, FAILED, NEEDS_DECISION, etc.)
   - Add iteration tracking for Ralph Wiggum loops

7. **Hot-Reload Safety Validation** ✓ (reload system exists)
   - Test reload on actual code changes
   - Verify rollback works
   - Add integration with worker completion

### Phase 2: Self-Hosting Bootstrap (The Goal)

8. **Ringmaster Self-Project Setup**
   - Create "ringmaster" project pointing to its own codebase
   - Add working directory configuration
   - Set up self-reference safety checks

9. **Bootstrap Sequence**
   - Script that starts Ringmaster
   - Creates initial self-improvement tasks
   - Spawns first worker
   - Validates end-to-end flow

10. **Self-Improvement Loop**
    - Detect when worker modifies Ringmaster code
    - Run tests automatically
    - Hot-reload if tests pass
    - Continue loop

### Phase 3: Production Polish (After self-hosting works)

11. Installation script
12. Backup automation
13. Priority inheritance
14. Capability registry
15. Cost tracking
16. Multi-user foundations

## Per-Cycle Instructions

Each marathon iteration, you MUST:

### 1. Assess Current State

- Read `prompts/PROGRESS-2.md`
- Check if API server is running: `curl http://localhost:8000/api/health`
- Check database: `ls -la .ringmaster/`
- Check for running workers
- Identify what blocks self-hosting

### 2. Select Next Work Unit

**IMPORTANT: Do exactly ONE task per iteration.**

Choose based on **self-hosting dependency order**:

**Priority 1: Hot-Reload Validation (CRITICAL)**
- Test hot-reload with actual code changes
- Verify tests run automatically after changes
- Validate module reloading works
- Confirm rollback on test failure
- **API server must stay running during reload**
- **This is THE make-or-break feature for self-hosting**

**Priority 2: Get API server running and stable**
- Start API server in background
- Test health endpoint
- Verify all core endpoints work
- Create systemd/service management

**Priority 2: Initialize database**
- Run migrations on fresh database
- Test all CRUD operations
- Verify data integrity

**Priority 3: Worker spawning integration**
- Test WorkerSpawner with actual tmux
- Create API endpoints: POST /api/workers/spawn
- Spawn real Claude Code worker
- Verify worker can pull tasks

**Priority 4: End-to-end task flow**
- Create task via API
- Verify enrichment works
- Check worker receives task
- Verify result reporting works

**Priority 5: Self-hosting setup**
- Add ringmaster as its own project
- Create bootstrap script
- Test full self-hosting loop

**Priority 6: Self-improvement validation**
- Worker modifies ringmaster code
- Tests run automatically
- Hot-reload triggers
- Verify new code is active

### 3. Implement

- Write production-quality code
- Add tests for new functionality
- Document any design decisions
- **Critical**: Test that changes don't break existing functionality

### 4. Validate

- Run linting: `ruff check .`
- Run tests: `pytest`
- For server/worker: Manual validation
- **For self-hosting**: Test the actual flow end-to-end

### 5. Checkpoint

```bash
# Commit changes
git add -A
git commit -m "feat(description): what was accomplished"
git push origin main

# Update PROGRESS-2.md with:
# - What was accomplished
# - Current self-hosting capability level
# - What blocks the next step
# - Next recommended task
```

### 6. Self-Hosting Readiness Check

**After each iteration, assess self-hosting capability:**

```
Can Ringmaster:
□ Start its own API server?
□ Initialize its own database?
□ Create tasks for itself?
□ Spawn workers to work on those tasks?
□ Receive and parse worker output?
□ Hot-reload when workers modify its code?
□ Continue operating while improving itself?
```

**When ALL checked:**
- Output: `<promise>SELF-HOSTING-CAPABLE</promise>`
- Create bootstrap script to demonstrate self-hosting
- Transition to self-improvement mode

## Stop Conditions

The marathon loop stops when:
- You output `<promise>SELF-HOSTING-CAPABLE</promise>` (goal achieved)
- External stop signal (user intervention)
- Circuit breaker trips (5+ consecutive errors)

## Important Notes

1. **Hot-reload is CRITICAL** - Ringmaster MUST reload its own code after workers modify it
2. **Worktree cleanup** - Workers MUST clean up git worktrees after task completion
3. **Self-hosting is the goal**, not production features
4. **Build in dependency order** - don't add features before core works
5. **Test everything** - self-hosting requires stability
6. **Keep it simple** - the loop must work reliably
7. **Document the bootstrap** - others need to understand how to start it

## Self-Hosting Requirements

For Ringmaster to work on itself, it needs:

1. **Hot-Reload**: After a worker modifies `src/ringmaster/` code:
   - File watcher detects changes
   - Tests run automatically
   - Modules reload on success
   - Rollback on failure
   - **API server continues serving throughout**

2. **Worktree Cleanup**: After each task:
   - Worker checks if worktree has changes
   - If clean: mark for cleanup
   - If has commits: keep for review
   - Stale worktrees pruned periodically

3. **Worker Isolation**: Each worker in its own git worktree:
   - Parallel execution without conflicts
   - Clean state for each task
   - Easy rollback of worker changes

## Current Iteration

Read `prompts/PROGRESS-2.md` and begin your cycle.
