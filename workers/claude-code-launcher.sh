#!/bin/bash
# Claude Code Launcher Script for Ringmaster
#
# This script launches Claude Code with customizable configuration.
# It reads environment variables set by Ringmaster:
#   RINGMASTER_PROMPT_FILE - Path to file containing the enriched prompt
#   RINGMASTER_WORKING_DIR - Working directory for the task
#   RINGMASTER_TASK_ID - Task/bead identifier
#   RINGMASTER_WORKER_ID - Worker identifier
#   RINGMASTER_LOG_FILE - Path to worker log file
#
# You can customize this script for your Claude Code setup:
# - Change the model (e.g., claude-opus-4-20250514 for Opus)
# - Add custom flags
# - Set environment variables for Claude Code

set -euo pipefail

# Default configuration
MODEL="${CLAUDE_MODEL:-claude-sonnet-4-20250514}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-}"
MAX_TOKENS="${CLAUDE_MAX_TOKENS:-200000}"

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

# Build Claude Code command
CLAUDE_CMD=(claude --print --dangerously-skip-permissions)

# Add model
CLAUDE_CMD+=(--model "$MODEL")

# Add config directory if specified
if [ -n "$CONFIG_DIR" ]; then
    export CLAUDE_CONFIG_DIR="$CONFIG_DIR"
fi

# Add max tokens if specified
if [ -n "$MAX_TOKENS" ]; then
    CLAUDE_CMD+=(--max-tokens "$MAX_TOKENS")
fi

# Add the prompt
CLAUDE_CMD+=(--prompt "$(cat "$RINGMASTER_PROMPT_FILE")")

# Log execution info
log "Task: ${RINGMASTER_TASK_ID:-unknown}"
log "Working in: $RINGMASTER_WORKING_DIR"
log "Model: $MODEL"
log "Running: ${CLAUDE_CMD[0]} ${CLAUDE_CMD[1]:+...}"

# Execute Claude Code
exec "${CLAUDE_CMD[@]}"
