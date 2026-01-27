-- Worker capabilities for task-worker matching
-- Based on docs/09-remaining-decisions.md

-- Add capabilities column to workers table (JSON array)
-- e.g., ["python", "typescript", "security", "refactoring"]
ALTER TABLE workers ADD COLUMN capabilities TEXT DEFAULT '[]';

-- Add required_capabilities column to tasks table (JSON array)
-- Workers must have ALL required capabilities to work on a task
ALTER TABLE tasks ADD COLUMN required_capabilities TEXT DEFAULT '[]';

-- Index for capability queries (extracted values from JSON)
-- Note: SQLite's JSON functions allow capability matching queries

INSERT OR IGNORE INTO _migrations (version, name) VALUES (6, '006_worker_capabilities');
