#!/bin/bash
# Z.AI GLM Launcher Script for Ringmaster
#
# This script launches a coding agent using Z.AI's GLM models.
# Z.AI provides access to GLM-4.7 and other models through their API.
#
# Environment variables:
#   ZAI_API_KEY - API key for Z.AI
#   ZAI_BASE_URL - Base URL for Z.AI API (default: https://api.z.ai/v1)
#   ZAI_MODEL - Model to use (default: glm-4.7)
#
# This launcher uses a generic approach that wraps any CLI tool
# configured to work with Z.AI's API.

set -euo pipefail

# Default configuration
MODEL="${ZAI_MODEL:-glm-4.7}"
API_KEY="${ZAI_API_KEY:-}"
BASE_URL="${ZAI_BASE_URL:-https://api.z.ai/v1}"

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

# Check if claude CLI is available (we can use it with custom API endpoint)
if ! command -v claude &> /dev/null; then
    log "ERROR: claude CLI not found. Please install Claude Code CLI first."
    log "  This launcher uses the Claude Code CLI with Z.AI's API endpoint."
    exit 1
fi

# Build command
CLAUDE_CMD=(claude --print --dangerously-skip-permissions)

# Add model (for tracking, actual model depends on API)
CLAUDE_CMD+=(--model "$MODEL")

# Add custom API endpoint
CLAUDE_CMD+=(--api-url "$BASE_URL")

# Add the prompt
CLAUDE_CMD+=(--prompt "$(cat "$RINGMASTER_PROMPT_FILE")")

# Log execution info
log "Task: ${RINGMASTER_TASK_ID:-unknown}"
log "Working in: $RINGMASTER_WORKING_DIR"
log "Model: $MODEL"
log "API Endpoint: $BASE_URL"
log "Running: ${CLAUDE_CMD[0]} ${CLAUDE_CMD[1]:+...}"

# Set API key as environment variable
if [ -n "$API_KEY" ]; then
    export ANTHROPIC_API_KEY="$API_KEY"
else
    log "WARNING: ZAI_API_KEY not set. The CLI may use its own configuration."
fi

# Execute Claude Code with Z.AI endpoint
exec "${CLAUDE_CMD[@]}"
