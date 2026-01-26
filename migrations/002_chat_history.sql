-- Chat history and RLM summaries
-- For context enrichment and conversation tracking

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    media_type TEXT,   -- text, audio, image
    media_path TEXT,   -- Path to original media file
    token_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_project ON chat_messages(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_task ON chat_messages(task_id, created_at);

-- Summaries table (RLM compressed history)
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    message_range_start INTEGER NOT NULL,
    message_range_end INTEGER NOT NULL,
    summary TEXT NOT NULL,
    key_decisions TEXT,  -- JSON array
    token_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_summaries_project ON summaries(project_id);
CREATE INDEX IF NOT EXISTS idx_summaries_range ON summaries(message_range_start, message_range_end);

INSERT OR IGNORE INTO _migrations (version, name) VALUES (2, '002_chat_history');
