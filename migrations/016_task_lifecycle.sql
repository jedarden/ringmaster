-- Task lifecycle tracking
-- Tracks task progress through deployment-model-specific steps

-- Add deployment configuration to projects
ALTER TABLE projects ADD COLUMN deployment_model TEXT DEFAULT 'none';
ALTER TABLE projects ADD COLUMN deployment_config TEXT;  -- JSON

-- Lifecycle records (one per task)
CREATE TABLE IF NOT EXISTS task_lifecycles (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    deployment_model TEXT NOT NULL DEFAULT 'none',
    steps TEXT NOT NULL,  -- JSON array of lifecycle steps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Index for fast lookup by task
CREATE INDEX IF NOT EXISTS idx_task_lifecycles_task_id ON task_lifecycles(task_id);

-- Index for listing by project
CREATE INDEX IF NOT EXISTS idx_task_lifecycles_project_id ON task_lifecycles(project_id);

-- Index for filtering by deployment model
CREATE INDEX IF NOT EXISTS idx_task_lifecycles_model ON task_lifecycles(deployment_model);
