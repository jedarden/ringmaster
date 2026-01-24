-- Session metrics for tracking token usage, costs, and performance

-------------------------------------------------------------------------------
-- SESSION METRICS TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_metrics (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    subscription TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    duration_seconds INTEGER DEFAULT 0,
    iterations INTEGER DEFAULT 0,
    success INTEGER DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_session_metrics_card ON session_metrics(card_id);
CREATE INDEX IF NOT EXISTS idx_session_metrics_platform ON session_metrics(platform);
CREATE INDEX IF NOT EXISTS idx_session_metrics_subscription ON session_metrics(subscription);
CREATE INDEX IF NOT EXISTS idx_session_metrics_started ON session_metrics(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_metrics_success ON session_metrics(success);
