-- Add outcome tracking columns for multi-signal task completion detection

-- Add blocked_reason to tasks table
ALTER TABLE tasks ADD COLUMN blocked_reason TEXT;

-- Add outcome tracking to session_metrics
ALTER TABLE session_metrics ADD COLUMN outcome TEXT;  -- success, likely_success, failed, likely_failed, needs_decision, unknown
ALTER TABLE session_metrics ADD COLUMN outcome_confidence REAL;  -- 0.0 to 1.0

-- Create index for outcome-based queries
CREATE INDEX IF NOT EXISTS idx_metrics_outcome ON session_metrics(outcome);

INSERT OR IGNORE INTO _migrations (version, name) VALUES (7, '007_outcome_tracking');
