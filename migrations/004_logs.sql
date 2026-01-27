-- Logs table for observability
-- Stores structured log entries for API access
-- Based on docs/09-remaining-decisions.md section 20

-- Logs table
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL CHECK(level IN ('debug', 'info', 'warning', 'error', 'critical')),
    component TEXT NOT NULL,  -- api, queue, enricher, scheduler, worker
    message TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    worker_id TEXT REFERENCES workers(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    data TEXT  -- JSON payload for additional context
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_component ON logs(component, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_task ON logs(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_logs_worker ON logs(worker_id) WHERE worker_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_logs_project ON logs(project_id) WHERE project_id IS NOT NULL;

-- Full-text search for log messages (optional but useful)
-- SQLite FTS5 for efficient text search
CREATE VIRTUAL TABLE IF NOT EXISTS logs_fts USING fts5(
    message,
    content='logs',
    content_rowid='id'
);

-- Triggers to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS logs_ai AFTER INSERT ON logs BEGIN
    INSERT INTO logs_fts(rowid, message) VALUES (new.id, new.message);
END;

CREATE TRIGGER IF NOT EXISTS logs_ad AFTER DELETE ON logs BEGIN
    INSERT INTO logs_fts(logs_fts, rowid, message) VALUES('delete', old.id, old.message);
END;

CREATE TRIGGER IF NOT EXISTS logs_au AFTER UPDATE ON logs BEGIN
    INSERT INTO logs_fts(logs_fts, rowid, message) VALUES('delete', old.id, old.message);
    INSERT INTO logs_fts(rowid, message) VALUES (new.id, new.message);
END;

-- Record migration
INSERT OR IGNORE INTO _migrations (version, name) VALUES (4, '004_logs');
