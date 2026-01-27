-- Add pinned column to projects table
-- Per docs/07-user-experience.md: Manual pinning is a ranking factor in the mailbox

-- Add pinned column (defaults to FALSE)
ALTER TABLE projects ADD COLUMN pinned BOOLEAN DEFAULT FALSE;

-- Index for efficient sorting (pinned projects first)
CREATE INDEX IF NOT EXISTS idx_projects_pinned ON projects(pinned DESC, updated_at DESC);

-- Track migration
INSERT OR IGNORE INTO _migrations (version, name) VALUES (12, '012_project_pinned');
