-- Session metrics for tracking worker performance and costs

CREATE TABLE IF NOT EXISTS session_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    worker_id TEXT NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,

    -- Token usage
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,

    -- Timing
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    duration_seconds INTEGER,

    -- Result
    success BOOLEAN,
    error_message TEXT,
    output_summary TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_metrics_task ON session_metrics(task_id);
CREATE INDEX IF NOT EXISTS idx_metrics_worker ON session_metrics(worker_id);
CREATE INDEX IF NOT EXISTS idx_metrics_created ON session_metrics(created_at);

-- Aggregated worker stats view
CREATE VIEW IF NOT EXISTS worker_stats AS
SELECT
    worker_id,
    COUNT(*) as total_sessions,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_sessions,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(estimated_cost_usd) as total_cost_usd,
    AVG(duration_seconds) as avg_duration_seconds,
    CAST(SUM(CASE WHEN success THEN 1 ELSE 0 END) AS REAL) / COUNT(*) as success_rate
FROM session_metrics
WHERE ended_at IS NOT NULL
GROUP BY worker_id;

INSERT OR IGNORE INTO _migrations (version, name) VALUES (3, '003_session_metrics');
