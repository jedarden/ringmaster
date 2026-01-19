-- Chat Messages Table extensions for RLM (Recursive Language Model) summarization
-- This adds columns needed for summarization and loop recovery

-- Add columns for summarization support if they don't exist
-- SQLite doesn't have ADD COLUMN IF NOT EXISTS, so we use a workaround
-- First check if the columns already exist by trying to select them

-- Note: These columns may not exist in older databases, the application code
-- handles the case where these columns are NULL or missing.

-- Add summarized flag column
ALTER TABLE chat_messages ADD COLUMN tokens_estimate INTEGER;

-- Update the tokens_estimate from existing tokens column where available
UPDATE chat_messages SET tokens_estimate = tokens WHERE tokens IS NOT NULL AND tokens_estimate IS NULL;

-- Add summarized flag
ALTER TABLE chat_messages ADD COLUMN summarized INTEGER DEFAULT 0;

-- Add summary group reference
ALTER TABLE chat_messages ADD COLUMN summary_group_id TEXT;

-- Index for summary groups
CREATE INDEX IF NOT EXISTS idx_chat_messages_summary ON chat_messages(summary_group_id);

-------------------------------------------------------------------------------
-- RLM Summaries Table - stores compressed summaries of chat history
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rlm_summaries (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    messages_summarized INTEGER NOT NULL,
    tokens_before INTEGER NOT NULL,
    tokens_after INTEGER NOT NULL,
    compression_ratio REAL NOT NULL,
    first_message_id TEXT NOT NULL,
    last_message_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rlm_summaries_card ON rlm_summaries(card_id);
CREATE INDEX IF NOT EXISTS idx_rlm_summaries_created ON rlm_summaries(card_id, created_at DESC);
