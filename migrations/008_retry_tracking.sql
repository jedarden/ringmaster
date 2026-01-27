-- Migration 008: Retry tracking
-- Adds columns for tracking retry timing and failure reasons

-- Add retry_after column for exponential backoff
-- Tasks with retry_after in the future should not be picked up by get_ready_tasks
ALTER TABLE tasks ADD COLUMN retry_after DATETIME;

-- Add last_failure_reason column to track why the last attempt failed
-- This helps with debugging and provides context for the next attempt
ALTER TABLE tasks ADD COLUMN last_failure_reason TEXT;

-- Index for efficient filtering of tasks ready for retry
CREATE INDEX IF NOT EXISTS idx_tasks_retry_after ON tasks(retry_after)
WHERE status = 'ready' AND retry_after IS NOT NULL;

-- Record migration
INSERT OR IGNORE INTO _migrations (version, name) VALUES (8, '008_retry_tracking');
