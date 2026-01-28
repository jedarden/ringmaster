#!/bin/bash
# Ringmaster Worker - Claude Code
# This script runs a Claude Code worker that pulls tasks from Ringmaster

set -e

# Configuration
WORKER_ID="${1:-claude-code-$(date +%s)}"
WORKTREE_PATH="${2:-/opt/ringmaster/projects.worktrees/$WORKER_ID}"
LOG_FILE="/var/log/ringmaster/workers/$WORKER_ID.log"
API_URL="${API_URL:-http://localhost:8000}"
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
CLAUDE_MODEL="${CLAUDE_MODEL:-claude-sonnet-4-20250514}"

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "$LOG_FILE" >&2
}

cleanup() {
    log "Worker $WORKER_ID shutting down"
    # Cleanup worktree if exists
    if [ -d "$WORKTREE_PATH" ]; then
        cd "$WORKTREE_PATH" 2>/dev/null || true
        git checkout main 2>/dev/null || true
        git branch -D "ringmaster-active" 2>/dev/null || true
    fi
}

trap cleanup EXIT TERM INT

log "Worker $WORKER_ID starting"
log "Model: $CLAUDE_MODEL"
log "Worktree: $WORKTREE_PATH"

# Main worker loop
ITERATION=0
while true; do
    # 1. Poll for available task
    log "Polling for available task..."
    TASK_JSON=$(ringmaster-cli pull-bead "$WORKER_ID" "[]" 2>&1)
    TASK_ID=$(echo "$TASK_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4 || true)

    if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "null" ]; then
        # No work available, wait and retry
        log "No task available, waiting 5 seconds..."
        sleep 5
        continue
    fi

    log "Picked up task $TASK_ID"
    ITERATION=0

    # 2. Build prompt from task context
    log "Building prompt for task $TASK_ID..."
    PROMPT=$(ringmaster-cli build-prompt "$TASK_ID" 2>&1)

    if [ -z "$PROMPT" ]; then
        error "Failed to build prompt for task $TASK_ID"
        ringmaster-cli report-result "$TASK_ID" "failed" 0 "Failed to build prompt"
        continue
    fi

    # 3. Prepare worktree
    log "Preparing worktree at $WORKTREE_PATH..."
    mkdir -p "$WORKTREE_PATH"

    # Initialize or update worktree
    if [ ! -d "$WORKTREE_PATH/.git" ]; then
        # Clone or copy project
        PROJECT_PATH=$(echo "$TASK_JSON" | grep -o '"project_path":"[^"]*' | cut -d'"' -f4 || true)
        if [ -n "$PROJECT_PATH" ] && [ -d "$PROJECT_PATH" ]; then
            log "Copying from $PROJECT_PATH"
            cp -r "$PROJECT_PATH" "$WORKTREE_PATH"
        fi
    fi

    cd "$WORKTREE_PATH" || {
        error "Failed to cd to $WORKTREE_PATH"
        ringmaster-cli report-result "$TASK_ID" "failed" 0 "Failed to access worktree"
        continue
    }

    # Create branch for this task
    git checkout -B "ringmaster-active" 2>/dev/null || git checkout -b "ringmaster-active"

    # 4. Ralph Wiggum loop - iterate until success or max iterations
    while [ $ITERATION -lt $MAX_ITERATIONS ]; do
        log "Iteration $((ITERATION + 1))/$MAX_ITERATIONS for task $TASK_ID"

        # Run Claude Code with the prompt
        log "Starting Claude Code execution..."

        # Write prompt to temp file
        PROMPT_FILE=$(mktemp)
        echo "$PROMPT" > "$PROMPT_FILE"

        # Run claude with appropriate flags
        claude \
            --print \
            --dangerously-skip-permissions \
            --model "$CLAUDE_MODEL" \
            --prompt "$PROMPT_FILE" \
            2>&1 | tee -a "$LOG_FILE"

        EXIT_CODE=${PIPESTATUS[0]}
        rm -f "$PROMPT_FILE"

        # 5. Detect outcome
        log "Claude Code exited with code $EXIT_CODE"

        # Run tests if available
        if [ -f "pyproject.toml" ] || [ -f "package.json" ] || [ -f "Cargo.toml" ]; then
            log "Running tests..."

            if [ -f "pyproject.toml" ]; then
                if pytest --quiet 2>&1 | tee -a "$LOG_FILE"; then
                    log "Tests passed!"
                    ringmaster-cli report-result "$TASK_ID" "completed" 0
                    break 2
                else
                    log "Tests failed, will retry..."
                fi
            elif [ -f "package.json" ]; then
                if npm test 2>&1 | tee -a "$LOG_FILE"; then
                    log "Tests passed!"
                    ringmaster-cli report-result "$TASK_ID" "completed" 0
                    break 2
                else
                    log "Tests failed, will retry..."
                fi
            fi
        fi

        # Check exit code
        if [ $EXIT_CODE -eq 0 ]; then
            # Check for success markers in output
            if tail -100 "$LOG_FILE" | grep -q "Task complete\|All tests passing\|Successfully completed"; then
                log "Task completed successfully"
                ringmaster-cli report-result "$TASK_ID" "completed" 0
                break 2
            fi
        fi

        # Check for decision needed
        if tail -100 "$LOG_FILE" | grep -q "Decision needed\|Need clarification"; then
            log "Task requires human decision"
            ringmaster-cli report-result "$TASK_ID" "needs_decision" 0
            break 2
        fi

        # Increment iteration and retry
        ITERATION=$((ITERATION + 1))

        if [ $ITERATION -ge $MAX_ITERATIONS ]; then
            log "Max iterations reached, reporting failure"
            ringmaster-cli report-result "$TASK_ID" "failed" $EXIT_CODE
            break 2
        fi

        log "Retrying... (iteration $ITERATION/$MAX_ITERATIONS)"
        sleep 2
    done

    # 6. Cleanup and commit
    log "Task $TASK_ID complete, cleaning up..."
    git add -A
    if git diff --staged --quiet; then
        log "No changes to commit"
    else
        git commit -m "Ringmaster task $TASK_ID (worker: $WORKER_ID)" || true
    fi

    git checkout main 2>/dev/null || true
    git branch -D "ringmaster-active" 2>/dev/null || true

    log "Task $TASK_ID finished, ready for next task"
done
