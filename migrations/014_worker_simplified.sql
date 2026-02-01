-- Worker Simplification Migration
-- Focus on LLM-generated start scripts instead of individual configuration fields

-- Add new columns for simplified worker model
ALTER TABLE workers ADD COLUMN description TEXT;

-- Add generated_script column for LLM-generated bash scripts
ALTER TABLE workers ADD COLUMN generated_script TEXT;

-- Mark old columns as deprecated (keep for backwards compatibility)
-- These columns will be ignored in new code but kept for existing data
-- command, args, prompt_flag, working_dir, timeout_seconds, env_vars
-- launcher_script, launcher_script_inline, launcher_args

-- Update migration tracking
INSERT INTO _migrations (version, name) VALUES (14, '014_worker_simplified');
