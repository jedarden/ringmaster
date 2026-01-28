#!/bin/bash
# Ringmaster Self-Hosting Bootstrap Script
# This script initializes and starts Ringmaster in self-hosting mode
# where it can receive tasks to improve itself.

set -e

# ============================================================================
# Configuration
# ============================================================================

RINGMASTER_DIR="${RINGMASTER_DIR:-/home/coder/ringmaster}"
RINGMASTER_DB="${RINGMASTER_DB:-$HOME/.ringmaster/ringmaster.db}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8080}"
WORKER_COUNT="${WORKER_COUNT:-1}"
WORKER_TYPE="${WORKER_TYPE:-claude-code}"
LOG_DIR="${HOME}/.ringmaster/logs"
PID_FILE="/tmp/ringmaster-api.pid"

# Ringmaster self-project configuration
SELF_PROJECT_NAME="Ringmaster"
SELF_PROJECT_REPO="file://${RINGMASTER_DIR}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# Utility Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

check_dependency() {
    if ! command -v "$1" &>/dev/null; then
        log_error "Missing dependency: $1"
        return 1
    fi
    return 0
}

wait_for_api() {
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s "http://localhost:${API_PORT}/health" | grep -q "healthy"; then
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done

    return 1
}

# ============================================================================
# Pre-flight Checks
# ============================================================================

preflight_checks() {
    log_step "Running pre-flight checks..."

    local missing=0

    # Check required dependencies
    for dep in python3 tmux curl jq sqlite3; do
        if ! check_dependency "$dep"; then
            missing=$((missing + 1))
        fi
    done

    # Check Ringmaster directory
    if [ ! -d "$RINGMASTER_DIR" ]; then
        log_error "Ringmaster directory not found: $RINGMASTER_DIR"
        missing=$((missing + 1))
    fi

    # Check Python package
    if ! python3 -c "import ringmaster" 2>/dev/null; then
        log_error "Ringmaster package not installed. Run: pip install -e $RINGMASTER_DIR"
        missing=$((missing + 1))
    fi

    # Check Claude Code (for claude-code workers)
    if [ "$WORKER_TYPE" = "claude-code" ]; then
        if ! check_dependency "claude"; then
            log_warn "Claude Code CLI not found - workers will fail to execute"
        fi
    fi

    if [ $missing -gt 0 ]; then
        log_error "Pre-flight checks failed with $missing errors"
        exit 1
    fi

    log_info "Pre-flight checks passed"
}

# ============================================================================
# Database Initialization
# ============================================================================

init_database() {
    log_step "Initializing database..."

    # Create database directory if needed
    mkdir -p "$(dirname "$RINGMASTER_DB")"

    # Run migrations
    cd "$RINGMASTER_DIR"
    python3 -m ringmaster.cli init --db "$RINGMASTER_DB" 2>/dev/null || true

    # Verify database exists
    if [ ! -f "$RINGMASTER_DB" ]; then
        log_error "Database initialization failed"
        exit 1
    fi

    log_info "Database initialized: $RINGMASTER_DB"
}

# ============================================================================
# API Server Management
# ============================================================================

check_api_running() {
    if curl -s "http://localhost:${API_PORT}/health" | grep -q "healthy"; then
        return 0
    fi
    return 1
}

start_api_server() {
    log_step "Starting API server..."

    # Check if already running
    if check_api_running; then
        log_info "API server already running on port $API_PORT"
        return 0
    fi

    # Start API server in background
    cd "$RINGMASTER_DIR"
    nohup python3 -m ringmaster.cli serve \
        --host "$API_HOST" \
        --port "$API_PORT" \
        > /tmp/ringmaster-api.log 2>&1 &

    echo $! > "$PID_FILE"

    # Wait for API to be ready
    log_info "Waiting for API server to start..."
    if wait_for_api; then
        log_info "API server started on http://localhost:${API_PORT}"
    else
        log_error "API server failed to start. Check /tmp/ringmaster-api.log"
        exit 1
    fi
}

stop_api_server() {
    log_step "Stopping API server..."

    if [ -f "$PID_FILE" ]; then
        kill "$(cat "$PID_FILE")" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi

    # Also kill by port
    fuser -k "$API_PORT/tcp" 2>/dev/null || true

    log_info "API server stopped"
}

# ============================================================================
# Self-Project Setup
# ============================================================================

ensure_self_project() {
    log_step "Ensuring self-project exists..."

    # Check if Ringmaster project exists
    local project_id
    project_id=$(curl -s "http://localhost:${API_PORT}/api/projects" | \
        jq -r '.[] | select(.name == "'"$SELF_PROJECT_NAME"'") | .id' | head -1)

    if [ -n "$project_id" ] && [ "$project_id" != "null" ]; then
        log_info "Self-project already exists: $project_id"
        echo "$project_id"
        return 0
    fi

    # Create self-project
    log_info "Creating self-project..."
    local response
    response=$(curl -s -X POST "http://localhost:${API_PORT}/api/projects" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "'"$SELF_PROJECT_NAME"'",
            "description": "Multi-Coding-Agent Orchestration Platform - Self-Hosting Bootstrap",
            "repo_url": "'"$SELF_PROJECT_REPO"'",
            "tech_stack": ["python", "fastapi", "sqlite", "react", "typescript"]
        }')

    project_id=$(echo "$response" | jq -r '.id')

    if [ -n "$project_id" ] && [ "$project_id" != "null" ]; then
        log_info "Self-project created: $project_id"
        echo "$project_id"
    else
        log_error "Failed to create self-project: $response"
        exit 1
    fi
}

# ============================================================================
# Worker Management
# ============================================================================

ensure_worker() {
    local worker_name="$1"
    local worker_type="$2"

    log_step "Ensuring worker exists: $worker_name ($worker_type)"

    # Check if worker exists
    local worker_id
    worker_id=$(curl -s "http://localhost:${API_PORT}/api/workers" | \
        jq -r '.[] | select(.name == "'"$worker_name"'") | .id' | head -1)

    if [ -n "$worker_id" ] && [ "$worker_id" != "null" ]; then
        log_info "Worker already exists: $worker_id"
        echo "$worker_id"
        return 0
    fi

    # Create worker via CLI (which handles database operations)
    cd "$RINGMASTER_DIR"
    local output
    output=$(python3 -m ringmaster.cli worker add "$worker_name" --type "$worker_type" 2>&1)

    # Extract worker ID from output
    worker_id=$(echo "$output" | grep -oP 'worker-[a-f0-9]+' | head -1)

    if [ -n "$worker_id" ]; then
        log_info "Worker created: $worker_id"

        # Activate worker
        python3 -m ringmaster.cli worker activate "$worker_id" 2>/dev/null || true

        echo "$worker_id"
    else
        log_error "Failed to create worker: $output"
        exit 1
    fi
}

spawn_worker_tmux() {
    local worker_id="$1"
    local worker_type="$2"

    log_step "Spawning worker in tmux: $worker_id"

    # Check if tmux session already exists
    local session_name="rm-worker-${worker_id}"
    if tmux has-session -t "$session_name" 2>/dev/null; then
        log_info "Worker tmux session already running: $session_name"
        return 0
    fi

    # Spawn via CLI
    cd "$RINGMASTER_DIR"
    python3 -m ringmaster.cli worker spawn "$worker_id" \
        --worktree "$RINGMASTER_DIR" 2>/dev/null || true

    # Verify session exists
    if tmux has-session -t "$session_name" 2>/dev/null; then
        log_info "Worker spawned: $session_name"
        log_info "Attach with: tmux attach-session -t $session_name"
    else
        log_warn "Worker spawn may have failed - check logs"
    fi
}

# ============================================================================
# Task Creation
# ============================================================================

create_selfimprovement_task() {
    local project_id="$1"
    local title="$2"
    local description="$3"
    local priority="${4:-P2}"

    log_step "Creating self-improvement task: $title"

    local response
    response=$(curl -s -X POST "http://localhost:${API_PORT}/api/tasks" \
        -H "Content-Type: application/json" \
        -d '{
            "project_id": "'"$project_id"'",
            "title": "'"$title"'",
            "description": "'"$description"'",
            "priority": "'"$priority"'"
        }')

    local task_id
    task_id=$(echo "$response" | jq -r '.id')

    if [ -n "$task_id" ] && [ "$task_id" != "null" ]; then
        # Mark task as ready
        curl -s -X PATCH "http://localhost:${API_PORT}/api/tasks/${task_id}" \
            -H "Content-Type: application/json" \
            -d '{"status": "ready"}' > /dev/null

        log_info "Task created and ready: $task_id"
        echo "$task_id"
    else
        log_error "Failed to create task: $response"
        return 1
    fi
}

# ============================================================================
# Bootstrap Sequence
# ============================================================================

bootstrap() {
    echo "============================================================"
    echo "         RINGMASTER SELF-HOSTING BOOTSTRAP"
    echo "============================================================"
    echo ""

    # Run pre-flight checks
    preflight_checks

    # Initialize database
    init_database

    # Start API server
    start_api_server

    # Ensure self-project exists
    local project_id
    project_id=$(ensure_self_project)

    # Create/ensure worker
    local worker_id
    worker_id=$(ensure_worker "selfhost-worker" "$WORKER_TYPE")

    # Optionally spawn worker in tmux
    if [ "${SPAWN_WORKER:-true}" = "true" ]; then
        spawn_worker_tmux "$worker_id" "$WORKER_TYPE"
    fi

    echo ""
    echo "============================================================"
    echo "         SELF-HOSTING BOOTSTRAP COMPLETE"
    echo "============================================================"
    echo ""
    echo "API Server:    http://localhost:${API_PORT}"
    echo "Project ID:    $project_id"
    echo "Worker ID:     $worker_id"
    echo ""
    echo "Next steps:"
    echo "  1. Create a task: POST http://localhost:${API_PORT}/api/tasks"
    echo "  2. Mark task ready: PATCH /api/tasks/{id} with {\"status\": \"ready\"}"
    echo "  3. Worker will pick up task automatically"
    echo ""
    echo "To attach to worker: tmux attach-session -t rm-worker-${worker_id}"
    echo "To view logs: tail -f /var/log/ringmaster/workers/${worker_id}.log"
    echo ""
}

# ============================================================================
# Demonstration Mode
# ============================================================================

demo() {
    echo "============================================================"
    echo "         RINGMASTER SELF-HOSTING DEMO"
    echo "============================================================"
    echo ""

    # First, run bootstrap
    bootstrap

    # Get project ID
    local project_id
    project_id=$(curl -s "http://localhost:${API_PORT}/api/projects" | \
        jq -r '.[] | select(.name == "Ringmaster") | .id' | head -1)

    if [ -z "$project_id" ]; then
        log_error "Could not find Ringmaster project"
        exit 1
    fi

    # Create a demo self-improvement task
    log_step "Creating demo self-improvement task..."

    create_selfimprovement_task "$project_id" \
        "Add docstring to bootstrap script" \
        "Add a comprehensive docstring at the top of scripts/bootstrap-selfhost.sh explaining what it does and how to use it." \
        "P3"

    echo ""
    echo "Demo task created! The worker will pick it up and execute it."
    echo "Watch the worker: tmux attach-session -t rm-worker-selfhost-worker"
    echo ""
}

# ============================================================================
# Status Check
# ============================================================================

status() {
    echo "============================================================"
    echo "         RINGMASTER SELF-HOSTING STATUS"
    echo "============================================================"
    echo ""

    # Check API
    echo -n "API Server: "
    if check_api_running; then
        echo -e "${GREEN}RUNNING${NC} (http://localhost:${API_PORT})"
    else
        echo -e "${RED}NOT RUNNING${NC}"
    fi

    # Check database
    echo -n "Database:   "
    if [ -f "$RINGMASTER_DB" ]; then
        local size
        size=$(du -h "$RINGMASTER_DB" | cut -f1)
        echo -e "${GREEN}EXISTS${NC} ($RINGMASTER_DB, $size)"
    else
        echo -e "${RED}NOT FOUND${NC}"
    fi

    # Check workers
    echo -n "Workers:    "
    local sessions
    sessions=$(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^rm-worker-' | wc -l || echo 0)
    if [ "$sessions" -gt 0 ]; then
        echo -e "${GREEN}$sessions RUNNING${NC}"
        tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^rm-worker-' | while read -r s; do
            echo "            - $s"
        done
    else
        echo -e "${YELLOW}NONE RUNNING${NC}"
    fi

    # Check pending tasks
    if check_api_running; then
        echo -n "Tasks:      "
        local ready_count
        ready_count=$(curl -s "http://localhost:${API_PORT}/api/tasks?status=ready" | jq 'length' 2>/dev/null || echo "?")
        local in_progress_count
        in_progress_count=$(curl -s "http://localhost:${API_PORT}/api/tasks?status=in_progress" | jq 'length' 2>/dev/null || echo "?")
        echo "Ready: $ready_count, In Progress: $in_progress_count"
    fi

    echo ""
}

# ============================================================================
# Main Entry Point
# ============================================================================

usage() {
    cat << EOF
Ringmaster Self-Hosting Bootstrap

Usage: $0 [command]

Commands:
    bootstrap   Initialize and start Ringmaster in self-hosting mode (default)
    demo        Run bootstrap and create a demo task
    status      Show current self-hosting status
    stop        Stop the API server
    help        Show this help message

Environment Variables:
    RINGMASTER_DIR   Ringmaster installation directory (default: /home/coder/ringmaster)
    RINGMASTER_DB    Database path (default: ~/.ringmaster/ringmaster.db)
    API_HOST         API server host (default: 0.0.0.0)
    API_PORT         API server port (default: 8080)
    WORKER_TYPE      Worker type: claude-code, aider, codex (default: claude-code)
    SPAWN_WORKER     Whether to spawn worker in tmux (default: true)

Examples:
    # Full bootstrap with default settings
    $0 bootstrap

    # Start with custom port
    API_PORT=9000 $0 bootstrap

    # Demo mode - creates a test task
    $0 demo

    # Check status
    $0 status
EOF
}

case "${1:-bootstrap}" in
    bootstrap)
        bootstrap
        ;;
    demo)
        demo
        ;;
    status)
        status
        ;;
    stop)
        stop_api_server
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        log_error "Unknown command: $1"
        usage
        exit 1
        ;;
esac
