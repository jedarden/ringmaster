-- Chat Messages Table for persisting conversation history
-- This enables RLM (Recursive Language Model) summarization and loop recovery

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    tokens_estimate INTEGER,
    summarized INTEGER DEFAULT 0,
    summary_group_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_card ON chat_messages(card_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(card_id, created_at ASC);
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
