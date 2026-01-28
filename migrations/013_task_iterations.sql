-- Migration 013: Task iteration tracking
-- Tracks the number of times a task has cycled through the work loop
-- This is different from attempts (failure retries) - iterations track
-- the "Ralph Wiggum loop" cycles for continuous improvement

-- Add iteration column to tasks table
-- Tracks current iteration count (0 = first iteration)
ALTER TABLE tasks ADD COLUMN iteration INTEGER DEFAULT 0;

-- Add max_iterations column to tasks table
-- When iteration >= max_iterations, task should be escalated for human review
ALTER TABLE tasks ADD COLUMN max_iterations INTEGER DEFAULT 10;

-- Index for efficient filtering of tasks needing escalation
CREATE INDEX IF NOT EXISTS idx_tasks_iteration ON tasks(iteration)
WHERE iteration > 0;

-- Record migration
INSERT OR IGNORE INTO _migrations (version, name) VALUES (13, '013_task_iterations');
