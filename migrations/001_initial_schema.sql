-- Ringmaster Initial Schema
-- Based on docs/05-state-persistence.md

-- Enable WAL mode for concurrent access
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tech_stack TEXT,  -- JSON array
    repo_url TEXT,
    settings TEXT,    -- JSON config overrides
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at);

-- Workers table (created before tasks to avoid circular FK)
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- claude-code, aider, codex, etc.
    status TEXT DEFAULT 'offline' CHECK(status IN ('idle', 'busy', 'offline')),
    current_task_id TEXT,  -- FK added later via trigger or app logic

    -- Configuration
    command TEXT NOT NULL,
    args TEXT,           -- JSON array
    prompt_flag TEXT DEFAULT '-p',
    working_dir TEXT,
    timeout_seconds INTEGER DEFAULT 1800,
    env_vars TEXT,       -- JSON object

    -- Stats
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    avg_completion_seconds REAL,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
CREATE INDEX IF NOT EXISTS idx_workers_type ON workers(type);

-- Tasks table (unified for epics, tasks, subtasks)
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK(type IN ('epic', 'task', 'subtask', 'decision', 'question')),

    title TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'P2' CHECK(priority IN ('P0', 'P1', 'P2', 'P3', 'P4')),
    status TEXT DEFAULT 'draft' CHECK(status IN (
        'draft', 'ready', 'assigned', 'in_progress',
        'blocked', 'review', 'done', 'failed'
    )),

    -- Execution tracking
    worker_id TEXT REFERENCES workers(id) ON DELETE SET NULL,
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
    prompt_path TEXT,
    output_path TEXT,
    context_hash TEXT,

    -- Epic-specific
    acceptance_criteria TEXT,  -- JSON array
    context TEXT,              -- RLM-processed context

    -- Decision-specific
    blocks_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    question TEXT,
    options TEXT,              -- JSON array
    recommendation TEXT,
    resolution TEXT,
    resolved_at DATETIME,

    -- Question-specific
    related_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    urgency TEXT DEFAULT 'medium' CHECK(urgency IN ('low', 'medium', 'high')),
    default_answer TEXT,
    answer TEXT,
    answered_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(combined_priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_worker ON tasks(worker_id);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type);

-- Dependencies table (task graph edges)
CREATE TABLE IF NOT EXISTS dependencies (
    child_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    parent_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (child_id, parent_id)
);

-- Prevent self-dependencies
CREATE TRIGGER IF NOT EXISTS prevent_self_dependency
BEFORE INSERT ON dependencies
BEGIN
    SELECT RAISE(ABORT, 'Task cannot depend on itself')
    WHERE NEW.child_id = NEW.parent_id;
END;

CREATE INDEX IF NOT EXISTS idx_deps_parent ON dependencies(parent_id);
CREATE INDEX IF NOT EXISTS idx_deps_child ON dependencies(child_id);

-- Queue table (materialized view of ready tasks)
CREATE TABLE IF NOT EXISTS queue (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    priority_score REAL NOT NULL,
    ready_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    assigned_at DATETIME,
    worker_id TEXT REFERENCES workers(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_queue_ready ON queue(ready_at) WHERE assigned_at IS NULL;

-- Events table (audit log)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    data TEXT,  -- JSON payload
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, created_at);

-- Migrations tracking
CREATE TABLE IF NOT EXISTS _migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO _migrations (version, name) VALUES (1, '001_initial_schema');
