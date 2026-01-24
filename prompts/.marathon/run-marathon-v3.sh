#!/bin/bash
# Marathon v3 Runner - Feature Completion Session
#
# This script runs a marathon coding session with proper JSON stream log capture.
# The prompt file is hot-reloadable - edit it to change behavior between iterations.

set -e

RINGMASTER_DIR="/home/coder/ringmaster"
PROMPT_FILE="$RINGMASTER_DIR/prompts/marathon-v3-feature-completion.md"
LOG_DIR="$RINGMASTER_DIR/prompts/.marathon/logs"
SESSION_ID="session_$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/${SESSION_ID}.jsonl"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Change to ringmaster directory
cd "$RINGMASTER_DIR"

echo "=============================================="
echo "  Ringmaster Marathon v3 - Feature Completion"
echo "=============================================="
echo ""
echo "  Prompt:    $PROMPT_FILE"
echo "  Log:       $LOG_FILE"
echo "  GitHub:    Issue #1 (jedarden/ringmaster)"
echo ""
echo "  Hot-reload: Edit the prompt file to adjust behavior"
echo "  JSON logs:  Stream output captured to $LOG_FILE"
echo ""
echo "=============================================="
echo ""

# Run claude with the marathon prompt
# --output-format stream-json captures all events in JSONL format
# --dangerously-skip-permissions enables autonomous operation
# Tee to both console and log file

claude \
  --output-format stream-json \
  --verbose \
  --dangerously-skip-permissions \
  --model claude-sonnet-4-20250514 \
  -p "$(cat "$PROMPT_FILE")" \
  2>&1 | tee "$LOG_FILE"

echo ""
echo "Session ended. Log saved to: $LOG_FILE"
