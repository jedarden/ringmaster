-- Migration 005: Action history for undo/redo functionality
--
-- Records all reversible actions with their inverse operations
-- Supports the reversibility UX principle from docs/07-user-experience.md

-- Action history table
CREATE TABLE IF NOT EXISTS action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Action metadata
    action_type TEXT NOT NULL,  -- 'task_created', 'task_updated', 'task_deleted', 'worker_assigned', etc.
    entity_type TEXT NOT NULL,  -- 'task', 'worker', 'project', 'dependency'
    entity_id TEXT NOT NULL,    -- ID of the affected entity

    -- State snapshots for undo/redo
    previous_state TEXT,        -- JSON snapshot before action (null for creates)
    new_state TEXT,             -- JSON snapshot after action (null for deletes)

    -- Scope
    project_id TEXT,            -- Project this action belongs to (null for global actions)

    -- Undo tracking
    undone INTEGER DEFAULT 0,   -- 1 if this action has been undone
    undone_at TIMESTAMP,        -- When the undo occurred

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- User/agent attribution
    actor_type TEXT DEFAULT 'user',  -- 'user', 'worker', 'system'
    actor_id TEXT                    -- Worker ID if actor_type='worker'
);

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_action_history_project ON action_history(project_id);
CREATE INDEX IF NOT EXISTS idx_action_history_entity ON action_history(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_action_history_created ON action_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_history_undone ON action_history(undone, created_at DESC);

-- Record migration
INSERT INTO _migrations (version, name, applied_at)
VALUES (5, 'action_history', CURRENT_TIMESTAMP);
