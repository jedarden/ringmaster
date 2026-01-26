# Remaining Architecture Decisions

## Overview

This document addresses remaining unclear areas in the Ringmaster architecture based on research and design decisions.

## 1. Bead Creation Flow

**Decision: User doesn't create beads directly. Bead-creator service handles it. User can edit after in a separate view.**

### Flow

```
User provides input (text/audio/image)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BEAD-CREATOR SERVICE                                                │
│                                                                      │
│  1. Parse and normalize input                                        │
│  2. Search existing beads for matches                                │
│     ├─ Match found → Update existing bead with new context          │
│     └─ No match → Create new bead(s)                                │
│  3. If epic/large → Decompose into smaller beads                    │
│  4. Set dependencies based on semantic analysis                      │
│  5. Assign priorities using PageRank                                 │
│  6. Queue beads for workers                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
User sees beads in mailbox (can edit/amend in separate view)
```

### User Editing

Editing beads is **not** the primary workflow. Users interact via conversation. However, a dedicated bead management view exists for:

- Amending bead descriptions
- Adjusting priorities manually
- Adding/removing dependencies
- Closing beads manually
- Splitting/merging beads

## 2. Epic Decomposition

**Decision: Bead-creator decomposes large beads. Workers can resubmit "too large" beads back to bead-creator.**

### Size Detection

```python
def is_bead_too_large(bead: Bead) -> bool:
    """Heuristic check if bead is too large for single worker."""

    signals = {
        "description_length": len(bead.description) > 2000,
        "multiple_components": count_components(bead.description) > 3,
        "multiple_concerns": count_concerns(bead.description) > 2,
        "keywords": any(kw in bead.description.lower() for kw in
                       ["and also", "additionally", "as well as", "multiple"]),
    }

    return sum(signals.values()) >= 2
```

### Worker Resubmission

```python
# Worker determines bead is too large
if worker.determines_too_large(bead):
    bead.status = "needs_decomposition"
    bead.resubmit_reason = "Bead contains multiple distinct concerns: [...]"
    queue.send_to_bead_creator(bead)
```

### Decomposition Strategy

```
Epic: "Build user authentication system"
        │
        ▼ Bead-creator decomposes
        │
        ├── Task: "Set up auth module structure"
        ├── Task: "Implement JWT token generation"
        ├── Task: "Implement token validation"
        ├── Task: "Add refresh token endpoint"
        └── Task: "Write integration tests"

Dependencies auto-detected and set.
```

## 3. Bead State Machine

**Decision: Follow [Yegge's Beads](https://github.com/steveyegge/beads) states: open, in_progress, blocked, closed.**

### States

```
┌──────────────────────────────────────────────────────────────────────┐
│                        BEAD STATE MACHINE                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                           ┌────────┐                                 │
│                           │  open  │ ← Initial state                │
│                           └───┬────┘                                 │
│                               │                                      │
│              ┌────────────────┼────────────────┐                     │
│              │                │                │                     │
│              ▼                ▼                ▼                     │
│       ┌───────────┐    ┌───────────┐    ┌──────────────┐            │
│       │in_progress│    │  blocked  │    │needs_decomp  │            │
│       └─────┬─────┘    └─────┬─────┘    └──────┬───────┘            │
│             │                │                  │                    │
│             │                │                  │                    │
│             │          (blocker resolved)       │                    │
│             │                │                  │                    │
│             │                ▼                  │                    │
│             │          ┌───────────┐            │                    │
│             └─────────►│in_progress│◄───────────┘                    │
│                        └─────┬─────┘     (after decomposition)       │
│                              │                                       │
│                              │                                       │
│                              ▼                                       │
│                        ┌──────────┐                                  │
│                        │  closed  │                                  │
│                        └──────────┘                                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### State Definitions

| State | Meaning | Transitions To |
|-------|---------|----------------|
| `open` | Ready for work, no blockers | `in_progress`, `blocked`, `needs_decomp` |
| `in_progress` | Worker actively working | `closed`, `blocked`, `open` (abandoned) |
| `blocked` | Waiting on dependency | `open` (when unblocked) |
| `needs_decomp` | Too large, sent to bead-creator | `open` (after decomposition creates children) |
| `closed` | Completed | (terminal) |

### Close Reasons

Per Beads convention, closing includes a reason:
```bash
bd close bd-1 --reason "Merged in PR #42"
bd close bd-2 --reason "Duplicate of bd-1"
bd close bd-3 --reason "No longer needed"
```

## 4. Worker Spawning

**Decision: On-demand spawning into tmux instances. Bash script with while loop wrapping headless CLI.**

### Worker Script Template

```bash
#!/bin/bash
# worker-claude-code.sh

WORKER_ID="${1:-claude-code-$(date +%s)}"
WORKTREE_PATH="${2:-/workspace/project.worktrees/$WORKER_ID}"
LOG_FILE="/var/log/ringmaster/workers/$WORKER_ID.log"

echo "[$(date)] Worker $WORKER_ID starting" >> "$LOG_FILE"

# Main loop
while true; do
    # 1. Poll for available bead
    BEAD_JSON=$(ringmaster-cli pull-bead --worker-id "$WORKER_ID" --capabilities "claude-code")

    if [ -z "$BEAD_JSON" ]; then
        # No work available, wait and retry
        sleep 5
        continue
    fi

    BEAD_ID=$(echo "$BEAD_JSON" | jq -r '.id')
    echo "[$(date)] Picked up bead $BEAD_ID" >> "$LOG_FILE"

    # 2. Prepare worktree
    cd "$WORKTREE_PATH" || exit 1
    git checkout -B "ringmaster/$BEAD_ID"

    # 3. Build prompt from bead context
    PROMPT=$(ringmaster-cli build-prompt --bead-id "$BEAD_ID")

    # 4. Run headless Claude Code
    claude --print --dangerously-skip-permissions \
        --model claude-sonnet-4-20250514 \
        --prompt "$PROMPT" \
        2>&1 | tee -a "$LOG_FILE"

    EXIT_CODE=$?

    # 5. Report result
    if [ $EXIT_CODE -eq 0 ]; then
        ringmaster-cli report-result --bead-id "$BEAD_ID" --status "completed"
    else
        ringmaster-cli report-result --bead-id "$BEAD_ID" --status "failed" --exit-code "$EXIT_CODE"
    fi

    # 6. Cleanup worktree
    git checkout main
    git branch -D "ringmaster/$BEAD_ID" 2>/dev/null

    echo "[$(date)] Finished bead $BEAD_ID" >> "$LOG_FILE"
done
```

### Tmux Spawning

```python
def spawn_worker(worker_type: str, worker_id: str) -> None:
    """Spawn worker in dedicated tmux session."""

    script = f"/opt/ringmaster/workers/worker-{worker_type}.sh"
    worktree = f"/workspace/project.worktrees/{worker_id}"

    # Create tmux session
    subprocess.run([
        "tmux", "new-session", "-d",
        "-s", f"worker-{worker_id}",
        f"{script} {worker_id} {worktree}"
    ])

    # Register worker in database
    db.execute("""
        INSERT INTO workers (id, type, status, tmux_session, started_at)
        VALUES (?, ?, 'idle', ?, ?)
    """, [worker_id, worker_type, f"worker-{worker_id}", now()])
```

### Worker Management Commands

```bash
# List workers
tmux list-sessions | grep worker-

# Attach to worker
tmux attach -t worker-claude-code-1

# Kill worker
tmux kill-session -t worker-claude-code-1
```

## 5. Worker Self-Selection (Pull Model)

**Decision: Ringmaster populates queue. Workers pull what they're capable of. Centralized capability memory.**

### Capability Registry

```sql
CREATE TABLE worker_capabilities (
    worker_type TEXT NOT NULL,
    capability TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,  -- Learned from reflexion
    PRIMARY KEY (worker_type, capability)
);

-- Example capabilities
INSERT INTO worker_capabilities VALUES
    ('claude-code', 'rust', 1.0),
    ('claude-code', 'typescript', 1.0),
    ('claude-code', 'security', 0.9),
    ('codex', 'python', 1.0),
    ('codex', 'refactoring', 0.95),
    ('aider', 'multi-file', 0.85);
```

### Bead Requirements

```sql
-- Beads can specify required capabilities
ALTER TABLE beads ADD COLUMN required_capabilities TEXT;  -- JSON array

-- Example
UPDATE beads SET required_capabilities = '["rust", "security"]' WHERE id = 'bd-a3f8';
```

### Pull Logic

```python
def pull_bead(worker_id: str, worker_type: str) -> Bead | None:
    """Worker pulls highest-priority bead it can handle."""

    # Get worker's capabilities
    capabilities = db.execute("""
        SELECT capability FROM worker_capabilities
        WHERE worker_type = ? AND confidence >= 0.7
    """, [worker_type]).fetchall()

    capability_set = {c[0] for c in capabilities}

    # Find best matching bead
    ready_beads = db.execute("""
        SELECT * FROM beads
        WHERE status = 'open'
        ORDER BY priority_score DESC
    """).fetchall()

    for bead in ready_beads:
        required = json.loads(bead.required_capabilities or '[]')

        # Check if worker has all required capabilities
        if set(required).issubset(capability_set):
            # Claim the bead
            db.execute("""
                UPDATE beads SET status = 'in_progress', worker_id = ?
                WHERE id = ? AND status = 'open'
            """, [worker_id, bead.id])

            if db.rowcount > 0:  # Successfully claimed
                return bead

    return None  # No suitable bead available
```

## 6. Worker Output Parsing

**Decision: Multi-signal approach: exit codes + structured markers + verification commands.**

### Research Findings

Per [InfoQ's CLI patterns for agents](https://www.infoq.com/articles/ai-agent-cli/):
- Exit codes should be documented and stable
- Agents run verification commands to confirm success
- Treat CLI output as stable API contracts

### Multi-Signal Detection

```python
def detect_outcome(worker_output: str, exit_code: int, bead: Bead) -> Outcome:
    """Detect task outcome using multiple signals."""

    signals = {
        "exit_code": exit_code == 0,
        "success_marker": any(m in worker_output for m in SUCCESS_MARKERS),
        "failure_marker": any(m in worker_output for m in FAILURE_MARKERS),
        "tests_passed": "tests passed" in worker_output.lower() or
                       "✓" in worker_output,
        "tests_failed": "tests failed" in worker_output.lower() or
                       "FAILED" in worker_output,
        "decision_needed": any(m in worker_output for m in DECISION_MARKERS),
    }

    # Decision needed takes priority
    if signals["decision_needed"]:
        return Outcome.NEEDS_DECISION

    # Explicit failure markers
    if signals["failure_marker"] or signals["tests_failed"]:
        return Outcome.FAILED

    # Explicit success markers + good exit code
    if signals["success_marker"] and signals["exit_code"]:
        return Outcome.SUCCESS

    # Tests passed is strong signal
    if signals["tests_passed"]:
        return Outcome.SUCCESS

    # Exit code alone (weak signal, but fallback)
    if signals["exit_code"]:
        return Outcome.LIKELY_SUCCESS
    else:
        return Outcome.LIKELY_FAILED

SUCCESS_MARKERS = [
    "✓ Task complete",
    "✓ All tests passing",
    "✓ Build successful",
    "Successfully completed",
    "DONE",
]

FAILURE_MARKERS = [
    "✗ Failed",
    "✗ Tests failing",
    "Error:",
    "FAILED",
    "Unable to complete",
]

DECISION_MARKERS = [
    "? Need clarification",
    "? Decision needed",
    "? Multiple options",
    "BLOCKED:",
]
```

### Prompt Workers to Emit Markers

Include in worker prompt:
```markdown
## Output Signals

When done, emit one of:
- ✓ Task complete (success)
- ✗ Failed: <reason> (failure)
- ? Decision needed: <question> (blocked)

Always run tests before declaring success.
```

## 7. Scheduling Cadence

**Decision: Workers poll when ready. No fixed cadence.**

```python
# In worker's while loop
while True:
    bead = pull_bead(worker_id, worker_type)

    if bead:
        work_on_bead(bead)
        # Immediately poll again when done
    else:
        # No work available, back off
        time.sleep(5)  # Configurable
```

### Backoff Strategy

```python
def poll_with_backoff(worker_id: str, worker_type: str) -> Bead | None:
    """Poll with exponential backoff when no work available."""

    backoff = 1  # seconds
    max_backoff = 60

    while True:
        bead = pull_bead(worker_id, worker_type)

        if bead:
            return bead

        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
```

## 8. User/Worker Conflict

**Decision: Last edit wins.**

Simple conflict resolution:
- Worker commits its changes
- If user edited same file, user's changes may be overwritten
- Git history preserves both versions
- User can revert if needed

For critical files, consider:
```toml
# ringmaster.toml
[conflict_resolution]
protected_files = ["config.toml", ".env.example"]
# Workers cannot modify protected files without user approval
```

## 9. Queue Starvation / Priority Inheritance

**Decision: If high-priority bead is blocked, its blocker inherits the higher priority.**

```python
def recalculate_priorities():
    """Priority inheritance: blockers inherit priority from blocked beads."""

    # Get all blocked beads
    blocked = db.execute("""
        SELECT b.id, b.priority_score, d.parent_id as blocker_id
        FROM beads b
        JOIN dependencies d ON b.id = d.child_id
        WHERE b.status = 'blocked'
    """).fetchall()

    for bead in blocked:
        blocker = db.execute("SELECT * FROM beads WHERE id = ?", [bead.blocker_id]).fetchone()

        if blocker and blocker.priority_score < bead.priority_score:
            # Inherit higher priority
            db.execute("""
                UPDATE beads SET priority_score = ?
                WHERE id = ?
            """, [bead.priority_score, blocker.id])

            log(f"Priority inheritance: {blocker.id} now {bead.priority_score} (blocking {bead.id})")
```

## 10. Long-Running Task Detection

**Decision: Heartbeat-based liveness + context degradation detection. No hard timeouts.**

### Research Findings

Per [Anthropic's guidance](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):
- Context degradation occurs around 20-30 minutes
- Agents start repeating themselves, forget constraints
- Heartbeats detect liveness

Per [Cursor's learnings](https://cursor.com/blog/scaling-agents):
- Agents occasionally run too long
- Periodic fresh starts combat drift

### Heartbeat Monitoring

```python
class WorkerMonitor:
    def __init__(self, worker_id: str, log_path: str):
        self.worker_id = worker_id
        self.log_path = log_path
        self.last_output_time = now()
        self.last_output_size = 0

    def check_liveness(self) -> LivenessStatus:
        """Check if worker is still producing output."""

        current_size = os.path.getsize(self.log_path)

        if current_size > self.last_output_size:
            self.last_output_time = now()
            self.last_output_size = current_size
            return LivenessStatus.ACTIVE

        idle_minutes = (now() - self.last_output_time).minutes

        if idle_minutes < 2:
            return LivenessStatus.THINKING
        elif idle_minutes < 10:
            return LivenessStatus.SLOW
        else:
            return LivenessStatus.LIKELY_HUNG

    def detect_degradation(self, recent_output: str) -> bool:
        """Detect context degradation (repetition, drift)."""

        # Check for repeated phrases
        lines = recent_output.split('\n')
        if len(lines) != len(set(lines)):
            return True  # Repetition detected

        # Check for constraint violations mentioned multiple times
        constraint_violations = recent_output.count("I apologize") + \
                               recent_output.count("I already tried")
        if constraint_violations > 3:
            return True

        return False
```

### Recovery Actions

| Status | Action |
|--------|--------|
| ACTIVE | None |
| THINKING | None (normal) |
| SLOW | Log warning |
| LIKELY_HUNG | Send interrupt signal, checkpoint, restart |
| DEGRADED | Force checkpoint, restart fresh with summary |

## 11. Partial Completion

**Decision: Worker loop handles retries. Beads track iteration count.**

Workers don't one-shot tasks. They iterate:

```bash
# Worker's Ralph loop
ITERATION=0
MAX_ITERATIONS=10

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    # Attempt implementation
    claude --print --prompt "$PROMPT" ...

    # Run tests
    if run_tests; then
        report_success
        break
    fi

    ITERATION=$((ITERATION + 1))
    # Update prompt with test failures for next iteration
done

if [ $ITERATION -eq $MAX_ITERATIONS ]; then
    report_failure "Max iterations reached"
fi
```

### Bead Iteration Tracking

```sql
ALTER TABLE beads ADD COLUMN iteration INTEGER DEFAULT 0;
ALTER TABLE beads ADD COLUMN max_iterations INTEGER DEFAULT 10;
```

## 12-20. Infrastructure & Operations

### 12. API Specification

Defer to implementation phase. Key endpoints:

| Endpoint | Purpose |
|----------|---------|
| `POST /api/input` | User submits text/audio/image |
| `GET /api/projects` | List projects (mailbox) |
| `GET /api/projects/{id}` | Project detail + beads |
| `GET /api/beads/{id}` | Bead detail |
| `PATCH /api/beads/{id}` | Update bead |
| `GET /api/workers` | Worker status |
| `WS /api/ws` | Real-time updates |

### 13-14. Authentication & TLS

Handled by Coder workspace environment:
- Coder provides authentication
- Port forwarding provides TLS
- Ringmaster trusts the workspace boundary

### 15. File Watching

Workers operating on beads will discover file changes:
- Git diff shows changes
- Worker context includes recent file state
- No explicit file watcher needed

### 16. Initial Setup

```bash
#!/bin/bash
# install-ringmaster.sh

# Prerequisites
apt-get install -y tmux sqlite3 python3.11 nodejs

# Clone ringmaster
git clone https://github.com/org/ringmaster.git /opt/ringmaster
cd /opt/ringmaster

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup frontend
cd ringmaster-ui && npm install && npm run build && cd ..

# Initialize database
python -m ringmaster.init_db

# Create systemd services
cp deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ringmaster-api ringmaster-queue ringmaster-enricher

# Start
systemctl start ringmaster-api ringmaster-queue ringmaster-enricher

echo "Ringmaster installed. Access at http://localhost:8080"
```

### 17. Project Onboarding

User says "clone repo X" → bead created → worker clones:

```
User: "Add the auth-service repo from github.com/org/auth-service"
        │
        ▼
Bead-creator:
  - Creates bead: "Clone auth-service repository"
  - Type: setup
  - Capabilities: ["git"]
        │
        ▼
Worker picks up bead:
  - git clone https://github.com/org/auth-service /workspace/auth-service
  - Initializes .beads/ directory
  - Reports success
        │
        ▼
Project appears in user's mailbox
```

### 18. Backup Strategy

SQLite to persisted disk:

```bash
# Hourly backup via cron
0 * * * * sqlite3 /opt/ringmaster/.ringmaster/ringmaster.db \
    ".backup /opt/ringmaster/backups/ringmaster_$(date +\%Y\%m\%d_\%H).db"

# Keep 7 days of hourly backups
find /opt/ringmaster/backups -mtime +7 -delete
```

### 19. Upgrade Path

Non-backwards-compatible upgrades:

1. Stop all workers
2. Backup database
3. Run migrations: `python -m ringmaster.migrate`
4. Restart services
5. Verify state compatibility

### 20. Observability / Logs

Ringmaster logs accessible via web UI:

```python
# API endpoint for logs
@app.get("/api/logs")
def get_logs(component: str, lines: int = 100):
    log_path = f"/var/log/ringmaster/{component}.log"
    return {"lines": tail(log_path, lines)}

# Workers can fetch logs for debugging
@app.get("/api/logs/for-bead")
def get_logs_for_bead(bead_id: str):
    """Get relevant logs to populate a debugging bead."""
    # Aggregate logs mentioning this bead or related errors
    return aggregate_relevant_logs(bead_id)
```

Log tab in web UI:
- Filter by component (api, queue, enricher, workers)
- Search
- Tail mode (live updates)

Workers diagnosing Ringmaster issues can request logs be added to their bead context.
