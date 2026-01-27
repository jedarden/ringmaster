-- Task outcomes table for reflexion-based learning
-- Stores task execution results for model routing optimization

CREATE TABLE IF NOT EXISTS task_outcomes (
    id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,

    -- Task signals (for similarity matching)
    file_count INTEGER DEFAULT 0,
    keywords TEXT,           -- JSON array
    bead_type TEXT NOT NULL, -- task, subtask, epic
    has_dependencies BOOLEAN DEFAULT FALSE,

    -- Execution context
    model_used TEXT NOT NULL,
    worker_type TEXT,        -- claude-code, aider, codex, goose, generic
    iterations INTEGER DEFAULT 1,
    duration_seconds INTEGER DEFAULT 0,

    -- Outcome
    success BOOLEAN NOT NULL,
    outcome TEXT,            -- SUCCESS, LIKELY_SUCCESS, FAILED, LIKELY_FAILED, NEEDS_DECISION
    confidence REAL DEFAULT 1.0,
    failure_reason TEXT,

    -- Reflection (generated post-task for learning)
    reflection TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient learning queries
CREATE INDEX IF NOT EXISTS idx_outcomes_project ON task_outcomes(project_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_model ON task_outcomes(model_used, success);
CREATE INDEX IF NOT EXISTS idx_outcomes_type ON task_outcomes(bead_type, success);
CREATE INDEX IF NOT EXISTS idx_outcomes_created ON task_outcomes(created_at);
