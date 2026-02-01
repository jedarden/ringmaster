#!/bin/bash
# Claude Code Launcher Script with Claude Max (claude-max-account)
#
# This script launches Claude Code using the claude-max-account CLI wrapper.
# Configure this for environments where you need to use a custom Claude Max account.
#
# Environment variables:
#   CLAUDE_MAX_API_KEY - API key for Claude Max account
#   CLAUDE_MAX_BASE_URL - Base URL for Claude Max API endpoint
#   CLAUDE_MAX_MODEL - Model to use (default: claude-sonnet-4-20250514)

set -euo pipefail

# Default configuration
MODEL="${CLAUDE_MAX_MODEL:-claude-sonnet-4-20250514}"
API_KEY="${CLAUDE_MAX_API_KEY:-}"
BASE_URL="${CLAUDE_MAX_BASE_URL:-}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >&2
}

# Validate required environment variables
if [ -z "${RINGMASTER_PROMPT_FILE:-}" ]; then
    log "ERROR: RINGMASTER_PROMPT_FILE not set"
    exit 1
fi

if [ -z "${RINGMASTER_WORKING_DIR:-}" ]; then
    log "ERROR: RINGMASTER_WORKING_DIR not set"
    exit 1
fi

# Check if API key is set (if using Claude Max)
if [ -n "$BASE_URL" ] && [ -z "$API_KEY" ]; then
    log "WARNING: CLAUDE_MAX_BASE_URL set but CLAUDE_MAX_API_KEY not set"
fi

# Check if prompt file exists
if [ ! -f "$RINGMASTER_PROMPT_FILE" ]; then
    log "ERROR: Prompt file not found: $RINGMASTER_PROMPT_FILE"
    exit 1
fi

# Change to working directory
cd "$RINGMASTER_WORKING_DIR" || {
    log "ERROR: Cannot change to working directory: $RINGMASTER_WORKING_DIR"
    exit 1
}

# Build Claude Code command
CLAUDE_CMD=(claude --print --dangerously-skip-permissions)

# Add model
CLAUDE_CMD+=(--model "$MODEL")

# Add custom API endpoint if configured
if [ -n "$BASE_URL" ]; then
    CLAUDE_CMD+=(--api-url "$BASE_URL")
fi

# Add the prompt
CLAUDE_CMD+=(--prompt "$(cat "$RINGMASTER_PROMPT_FILE")")

# Log execution info (without sensitive data)
log "Task: ${RINGMASTER_TASK_ID:-unknown}"
log "Working in: $RINGMASTER_WORKING_DIR"
log "Model: $MODEL"
if [ -n "$BASE_URL" ]; then
    log "API Endpoint: $BASE_URL"
fi
log "Running: ${CLAUDE_CMD[0]} ${CLAUDE_CMD[1]:+...}"

# Set API key as environment variable if provided
if [ -n "$API_KEY" ]; then
    export ANTHROPIC_API_KEY="$API_KEY"
fi

# Execute Claude Code
exec "${CLAUDE_CMD[@]}"
