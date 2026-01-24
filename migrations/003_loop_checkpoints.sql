-- Loop checkpoints for session resumption
-- This table stores checkpoint data for interrupted loop recovery

-------------------------------------------------------------------------------
-- LOOP CHECKPOINTS TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS loop_checkpoints (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    platform TEXT NOT NULL,
    subscription TEXT,
    state_json TEXT NOT NULL,
    last_prompt TEXT,
    last_response_summary TEXT,
    modified_files TEXT DEFAULT '[]',
    checkpoint_commit TEXT,
    total_cost_usd REAL DEFAULT 0.0,
    total_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_loop_checkpoints_card ON loop_checkpoints(card_id);
CREATE INDEX IF NOT EXISTS idx_loop_checkpoints_iteration ON loop_checkpoints(card_id, iteration DESC);
CREATE INDEX IF NOT EXISTS idx_loop_checkpoints_created ON loop_checkpoints(created_at DESC);
