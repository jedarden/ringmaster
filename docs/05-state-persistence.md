# State Persistence

## Overview

Ringmaster uses **SQLite + files** for state persistence. All circus acts (workers) run on the same server and access state directly—no network overhead, no distributed complexity.

## Design Principles

1. **SQLite for structured data** - Tasks, workers, queue state, metrics
2. **Files for content** - Prompts, outputs, context, summaries
3. **Single server** - All workers access the same SQLite instance
4. **WAL mode** - Concurrent reads, serialized writes
5. **JSONL for Beads compat** - Export/import with Steve Yegge's format

## Directory Structure

```
.ringmaster/
├── ringmaster.db           # SQLite database
├── ringmaster.db-wal       # Write-ahead log
├── ringmaster.db-shm       # Shared memory
│
├── projects/
│   └── {project_id}/
│       ├── project.md      # Project description
│       ├── conventions.md  # Coding conventions
│       ├── context/
│       │   ├── adrs/       # Architecture decisions
│       │   ├── libs/       # Library documentation
│       │   └── examples/   # Reference code
│       └── history/
│           └── summaries/  # RLM chat summaries
│
├── tasks/
│   └── {task_id}/
│       ├── prompt.md       # Enriched prompt sent to worker
│       ├── output.log      # Worker stdout/stderr
│       ├── context.json    # Snapshot of context used
│       └── iterations/
│           ├── 001.log     # First attempt
│           ├── 002.log     # Second attempt
│           └── ...
│
├── workers/
│   └── {worker_id}/
│       ├── current.pid     # Process ID if running
│       └── session.log     # Current session output
│
└── exports/
    └── beads.jsonl         # Beads-compatible export
```

## SQLite Schema

### Projects Table

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tech_stack TEXT,           -- JSON array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    settings TEXT              -- JSON config overrides
);

CREATE INDEX idx_projects_updated ON projects(updated_at);
```

### Tasks Table

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,                    -- bd-xxxx or bd-xxxx.n
    project_id TEXT NOT NULL REFERENCES projects(id),
    parent_id TEXT REFERENCES tasks(id),    -- NULL for epics
    type TEXT NOT NULL CHECK(type IN ('epic', 'task', 'subtask', 'decision', 'question')),

    title TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'P2' CHECK(priority IN ('P0', 'P1', 'P2', 'P3', 'P4')),
    status TEXT DEFAULT 'draft' CHECK(status IN (
        'draft', 'ready', 'assigned', 'in_progress',
        'blocked', 'review', 'done', 'failed'
    )),

    -- Execution tracking
    worker_id TEXT REFERENCES workers(id),
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,

    -- Graph metrics (cached)
    pagerank_score REAL DEFAULT 0,
    betweenness_score REAL DEFAULT 0,
    on_critical_path BOOLEAN DEFAULT FALSE,
    combined_priority REAL DEFAULT 0,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,

    -- File references
    prompt_path TEXT,          -- Path to enriched prompt
    output_path TEXT,          -- Path to worker output
    context_hash TEXT          -- SHA256 of context used
);

CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_priority ON tasks(combined_priority DESC);
CREATE INDEX idx_tasks_parent ON tasks(parent_id);
CREATE INDEX idx_tasks_worker ON tasks(worker_id);
```

### Dependencies Table

```sql
CREATE TABLE dependencies (
    child_id TEXT NOT NULL REFERENCES tasks(id),
    parent_id TEXT NOT NULL REFERENCES tasks(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (child_id, parent_id)
);

-- Prevent self-dependencies
CREATE TRIGGER prevent_self_dependency
BEFORE INSERT ON dependencies
BEGIN
    SELECT RAISE(ABORT, 'Task cannot depend on itself')
    WHERE NEW.child_id = NEW.parent_id;
END;

CREATE INDEX idx_deps_parent ON dependencies(parent_id);
CREATE INDEX idx_deps_child ON dependencies(child_id);
```

### Workers Table

```sql
CREATE TABLE workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,        -- claude-code, codex, aider, etc.
    status TEXT DEFAULT 'idle' CHECK(status IN ('idle', 'busy', 'offline')),
    current_task_id TEXT REFERENCES tasks(id),

    -- Configuration (from ringmaster.toml, cached here)
    command TEXT NOT NULL,
    args TEXT,                 -- JSON array
    prompt_flag TEXT,
    working_dir TEXT,
    timeout_seconds INTEGER DEFAULT 1800,

    -- Stats
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    avg_completion_seconds REAL,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME
);

CREATE INDEX idx_workers_status ON workers(status);
CREATE INDEX idx_workers_type ON workers(type);
```

### Queue Table

```sql
-- Materialized view of ready tasks, ordered by priority
CREATE TABLE queue (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
    priority_score REAL NOT NULL,
    ready_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    assigned_at DATETIME,
    worker_id TEXT REFERENCES workers(id)
);

CREATE INDEX idx_queue_priority ON queue(priority_score DESC);
CREATE INDEX idx_queue_ready ON queue(ready_at) WHERE assigned_at IS NULL;
```

### Chat History Table

```sql
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    task_id TEXT REFERENCES tasks(id),     -- NULL for project-level chat
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    media_type TEXT,           -- text, audio, image
    media_path TEXT,           -- Path to original media file
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_project ON chat_messages(project_id, created_at);
CREATE INDEX idx_chat_task ON chat_messages(task_id, created_at);
```

### Summaries Table

```sql
CREATE TABLE summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    task_id TEXT REFERENCES tasks(id),
    message_range_start INTEGER NOT NULL,  -- First message ID included
    message_range_end INTEGER NOT NULL,    -- Last message ID included
    summary TEXT NOT NULL,
    key_decisions TEXT,        -- JSON array of decisions
    token_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_summaries_project ON summaries(project_id);
CREATE INDEX idx_summaries_range ON summaries(message_range_start, message_range_end);
```

### Events Table (Audit Log)

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,  -- task_created, task_assigned, task_completed, etc.
    entity_type TEXT NOT NULL, -- project, task, worker, etc.
    entity_id TEXT NOT NULL,
    data TEXT,                 -- JSON payload
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_entity ON events(entity_type, entity_id);
CREATE INDEX idx_events_type ON events(event_type, created_at);
```

## SQLite Configuration

```sql
-- Enable WAL mode for concurrent access
PRAGMA journal_mode = WAL;

-- Synchronous NORMAL for balance of safety and speed
PRAGMA synchronous = NORMAL;

-- Increase cache size (10MB)
PRAGMA cache_size = -10000;

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Busy timeout for lock contention
PRAGMA busy_timeout = 5000;
```

## File Storage

### Prompt Files

Enriched prompts are stored as markdown:

```markdown
<!-- .ringmaster/tasks/bd-a3f8.1/prompt.md -->

# Task: bd-a3f8.1

## Objective
Implement JWT token generation

## Project Context
This is an authentication service using Rust/Axum...

## Recent History
[Summary of relevant conversation]

## Relevant Code
```rust
// src/auth/mod.rs
...
```

## Requirements
...

## Acceptance Criteria
...
```

### Output Files

Worker output is stored with timestamps:

```
<!-- .ringmaster/tasks/bd-a3f8.1/output.log -->

[2026-01-26T10:30:00Z] Worker: claude-code-1
[2026-01-26T10:30:00Z] Starting iteration 1

... worker stdout/stderr ...

[2026-01-26T10:45:00Z] ✓ Task complete
[2026-01-26T10:45:00Z] Duration: 15m 00s
```

### Iteration History

Each Ralph loop iteration is preserved:

```
.ringmaster/tasks/bd-a3f8.1/iterations/
├── 001.log    # First attempt - tests failed
├── 002.log    # Second attempt - compilation error
├── 003.log    # Third attempt - success
└── metadata.json
```

```json
// metadata.json
{
  "total_iterations": 3,
  "successful_iteration": 3,
  "total_duration_seconds": 2700,
  "iterations": [
    {"number": 1, "result": "tests_failed", "duration": 900},
    {"number": 2, "result": "compilation_error", "duration": 600},
    {"number": 3, "result": "success", "duration": 1200}
  ]
}
```

## Concurrent Access

### Write Serialization

SQLite handles write serialization automatically with WAL mode. Workers acquire a write lock briefly:

```python
# Pseudo-code for task assignment
def assign_task_to_worker(worker_id: str) -> Task | None:
    with db.transaction():
        # Lock and fetch highest priority ready task
        task = db.execute("""
            SELECT * FROM queue
            WHERE assigned_at IS NULL
            ORDER BY priority_score DESC
            LIMIT 1
            FOR UPDATE
        """).fetchone()

        if task:
            db.execute("""
                UPDATE queue SET assigned_at = ?, worker_id = ?
                WHERE task_id = ?
            """, [now(), worker_id, task.id])

            db.execute("""
                UPDATE tasks SET status = 'assigned', worker_id = ?
                WHERE id = ?
            """, [worker_id, task.id])

            return task
    return None
```

### Read Concurrency

Multiple workers can read simultaneously:

```python
# Workers can read task details concurrently
def get_task_context(task_id: str) -> TaskContext:
    task = db.execute("SELECT * FROM tasks WHERE id = ?", [task_id]).fetchone()
    deps = db.execute("SELECT * FROM dependencies WHERE child_id = ?", [task_id]).fetchall()
    # No locking needed for reads
    return TaskContext(task, deps)
```

## Backup & Recovery

### Automatic Backups

```bash
# Hourly backup via cron
0 * * * * sqlite3 .ringmaster/ringmaster.db ".backup .ringmaster/backups/ringmaster_$(date +%Y%m%d_%H%M).db"
```

### Point-in-Time Recovery

WAL files enable recovery to any point:

```bash
# Restore to specific backup
cp .ringmaster/backups/ringmaster_20260126_1000.db .ringmaster/ringmaster.db
```

## Beads Export/Import

### Export to Beads Format

```python
def export_to_beads(project_id: str, output_path: str):
    tasks = db.execute("""
        SELECT t.*, GROUP_CONCAT(d.parent_id) as deps
        FROM tasks t
        LEFT JOIN dependencies d ON t.id = d.child_id
        WHERE t.project_id = ?
        GROUP BY t.id
    """, [project_id]).fetchall()

    with open(output_path, 'w') as f:
        for task in tasks:
            bead = {
                "id": task.id,
                "title": task.title,
                "status": "open" if task.status != "done" else "closed",
                "priority": task.priority,
                "deps": task.deps.split(',') if task.deps else []
            }
            f.write(json.dumps(bead) + '\n')
```

### Import from Beads

```python
def import_from_beads(project_id: str, input_path: str):
    with db.transaction():
        with open(input_path) as f:
            for line in f:
                bead = json.loads(line)
                db.execute("""
                    INSERT INTO tasks (id, project_id, title, status, priority)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        status = excluded.status
                """, [bead['id'], project_id, bead['title'],
                      'done' if bead['status'] == 'closed' else 'ready',
                      bead.get('priority', 'P2')])

                for dep_id in bead.get('deps', []):
                    db.execute("""
                        INSERT OR IGNORE INTO dependencies (child_id, parent_id)
                        VALUES (?, ?)
                    """, [bead['id'], dep_id])
```

## Configuration

```toml
# ringmaster.toml

[storage]
db_path = ".ringmaster/ringmaster.db"
files_path = ".ringmaster"

# SQLite tuning
wal_mode = true
cache_size_mb = 10
busy_timeout_ms = 5000

# Backups
backup_enabled = true
backup_interval_hours = 1
backup_retention_days = 7

# Cleanup
cleanup_completed_tasks_days = 30
cleanup_iteration_logs_days = 7
```
