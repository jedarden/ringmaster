-- Add needs_decomposition status for task resubmission
-- This status indicates a task was deemed too large by a worker
-- and needs to be decomposed by the BeadCreator service.

-- SQLite doesn't support ALTER TABLE to modify CHECK constraints directly.
-- We need to recreate the table with the new constraint.

-- Step 1: Create a new table with updated CHECK constraint
CREATE TABLE IF NOT EXISTS tasks_new (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK(type IN ('epic', 'task', 'subtask', 'decision', 'question')),

    title TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'P2' CHECK(priority IN ('P0', 'P1', 'P2', 'P3', 'P4')),
    status TEXT DEFAULT 'draft' CHECK(status IN (
        'draft', 'ready', 'assigned', 'in_progress',
        'blocked', 'needs_decomposition', 'review', 'done', 'failed'
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
    answered_at DATETIME,

    -- Capabilities (added in migration 006)
    required_capabilities TEXT,  -- JSON array

    -- Outcome tracking (added in migration 007)
    blocked_reason TEXT,

    -- Retry tracking (added in migration 008)
    retry_after DATETIME,
    last_failure_reason TEXT
);

-- Step 2: Copy data from old table to new table
INSERT INTO tasks_new (
    id, project_id, parent_id, type, title, description, priority, status,
    worker_id, attempts, max_attempts, pagerank_score, betweenness_score,
    on_critical_path, combined_priority, created_at, updated_at, started_at,
    completed_at, prompt_path, output_path, context_hash, acceptance_criteria,
    context, blocks_id, question, options, recommendation, resolution,
    resolved_at, related_id, urgency, default_answer, answer, answered_at,
    required_capabilities, blocked_reason, retry_after, last_failure_reason
)
SELECT
    id, project_id, parent_id, type, title, description, priority, status,
    worker_id, attempts, max_attempts, pagerank_score, betweenness_score,
    on_critical_path, combined_priority, created_at, updated_at, started_at,
    completed_at, prompt_path, output_path, context_hash, acceptance_criteria,
    context, blocks_id, question, options, recommendation, resolution,
    resolved_at, related_id, urgency, default_answer, answer, answered_at,
    required_capabilities, blocked_reason, retry_after, last_failure_reason
FROM tasks;

-- Step 3: Drop the old table
DROP TABLE tasks;

-- Step 4: Rename the new table to the original name
ALTER TABLE tasks_new RENAME TO tasks;

-- Step 5: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(combined_priority DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_worker ON tasks(worker_id);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type);

-- Record migration
INSERT OR IGNORE INTO _migrations (version, name) VALUES (9, '009_needs_decomposition_status');
