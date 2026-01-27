-- Migration 010: Context assembly logs for enrichment observability
--
-- Per docs/04-context-enrichment.md "Observability" section:
-- Track what context is being assembled for each task to enable
-- debugging, analysis, and improvement of the enrichment pipeline.

-- Context assembly logs table
CREATE TABLE IF NOT EXISTS context_assembly_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Task and project reference
    task_id TEXT NOT NULL,
    project_id TEXT NOT NULL,

    -- Assembly metrics
    sources_queried TEXT,           -- JSON array of source names queried
    candidates_found INTEGER,       -- Total candidate items found
    items_included INTEGER,         -- Items that made it into final context
    tokens_used INTEGER,            -- Actual tokens used
    tokens_budget INTEGER,          -- Token budget for this assembly

    -- Compression tracking
    compression_applied TEXT,       -- JSON array of sources that were compressed
    compression_ratio REAL,         -- Overall compression ratio (0-1)

    -- Stage tracking
    stages_applied TEXT,            -- JSON array of stages that contributed content

    -- Performance
    assembly_time_ms INTEGER,       -- Time to assemble context in milliseconds

    -- Context hash for deduplication detection
    context_hash TEXT,              -- SHA256 prefix of assembled context

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_context_assembly_task ON context_assembly_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_context_assembly_project ON context_assembly_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_context_assembly_created ON context_assembly_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_context_assembly_tokens ON context_assembly_logs(tokens_used);

-- Record migration
INSERT INTO _migrations (version, name, applied_at)
VALUES (10, 'context_assembly_logs', CURRENT_TIMESTAMP);
