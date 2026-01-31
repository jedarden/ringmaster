-- Add prompt_template column to workers table
-- This template is injected when the worker executes a task
-- Supports placeholders: {task}, {context}, {project}, {capabilities}

ALTER TABLE workers ADD COLUMN prompt_template TEXT;
