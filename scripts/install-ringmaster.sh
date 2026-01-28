#!/bin/bash
# Ringmaster Installation Script
# This script installs Ringmaster for production use

set -e

# Configuration
INSTALL_DIR="/opt/ringmaster"
REPO_URL="${REPO_URL:-https://github.com/jedarden/ringmaster.git}"
BRANCH="${BRANCH:-main}"
SERVICE_USER="ringmaster"
PYTHON_VERSION="3.11"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    log_error "Cannot detect OS. Exiting."
    exit 1
fi

log_info "Detected OS: $OS"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (use sudo)"
    exit 1
fi

# Create service user if not exists
if ! id "$SERVICE_USER" &>/dev/null; then
    log_info "Creating service user: $SERVICE_USER"
    useradd -r -s /bin/bash -d "$INSTALL_DIR" "$SERVICE_USER"
else
    log_info "Service user $SERVICE_USER already exists"
fi

# Install dependencies based on OS
log_info "Installing system dependencies..."
if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    apt-get update
    apt-get install -y \
        tmux \
        sqlite3 \
        python3 \
        python3-venv \
        python3-dev \
        nodejs \
        npm \
        git \
        curl
elif [ "$OS" = "fedora" ] || [ "$OS" = "rhel" ] || [ "$OS" = "centos" ]; then
    dnf install -y \
        tmux \
        sqlite \
        python3 \
        python3-devel \
        nodejs \
        npm \
        git \
        curl
else
    log_warn "Unknown OS $OS, attempting to install with apt-get"
    apt-get update
    apt-get install -y tmux sqlite3 python3 python3-venv python3-dev nodejs npm git curl
fi

# Clone or update repository
if [ -d "$INSTALL_DIR/.git" ]; then
    log_info "Repository exists, pulling latest changes..."
    cd "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" git fetch
    sudo -u "$SERVICE_USER" git checkout "$BRANCH"
    sudo -u "$SERVICE_USER" git pull
else
    log_info "Cloning repository to $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create Python virtual environment
log_info "Setting up Python virtual environment..."
sudo -u "$SERVICE_USER" python3 -m venv venv
sudo -u "$SERVICE_USER" venv/bin/pip install --upgrade pip

# Install Python requirements
if [ -f "requirements.txt" ]; then
    log_info "Installing Python requirements..."
    sudo -u "$SERVICE_USER" venv/bin/pip install -r requirements.txt
else
    log_warn "requirements.txt not found, skipping Python packages"
fi

# Build frontend
if [ -d "frontend" ]; then
    log_info "Building frontend..."
    cd frontend
    sudo -u "$SERVICE_USER" npm install
    sudo -u "$SERVICE_USER" npm run build
    cd "$INSTALL_DIR"
else
    log_warn "Frontend directory not found, skipping frontend build"
fi

# Create necessary directories
log_info "Creating data directories..."
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/output"
mkdir -p "$INSTALL_DIR/projects"
mkdir -p "/var/log/ringmaster"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/logs"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/output"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/projects"
chown -R "$SERVICE_USER:$SERVICE_USER" "/var/log/ringmaster"

# Initialize database
log_info "Initializing database..."
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/python" -m ringmaster.cli init || true

# Create systemd service files
log_info "Creating systemd services..."

# Ringmaster API service
cat > /etc/systemd/system/ringmaster-api.service << 'EOF'
[Unit]
Description=Ringmaster API Server
After=network.target

[Service]
Type=simple
User=ringmaster
WorkingDirectory=/opt/ringmaster
Environment="PATH=/opt/ringmaster/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="RINGMASTER_DATABASE_PATH=/opt/ringmaster/data/ringmaster.db"
Environment="RINGMASTER_LOG_LEVEL=info"
Environment="RINGMASTER_OUTPUT_DIR=/opt/ringmaster/output"
ExecStart=/opt/ringmaster/venv/bin/python -m ringmaster.cli serve --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/var/log/ringmaster/api.log
StandardError=append:/var/log/ringmaster/api.error.log

[Install]
WantedBy=multi-user.target
EOF

# Ringmaster Scheduler service
cat > /etc/systemd/system/ringmaster-scheduler.service << 'EOF'
[Unit]
Description=Ringmaster Task Scheduler
After=network.target ringmaster-api.service

[Service]
Type=simple
User=ringmaster
WorkingDirectory=/opt/ringmaster
Environment="PATH=/opt/ringmaster/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="RINGMASTER_DATABASE_PATH=/opt/ringmaster/data/ringmaster.db"
Environment="RINGMASTER_LOG_LEVEL=info"
Environment="RINGMASTER_OUTPUT_DIR=/opt/ringmaster/output"
ExecStart=/opt/ringmaster/venv/bin/python -m ringmaster.cli scheduler
Restart=always
RestartSec=10
StandardOutput=append:/var/log/ringmaster/scheduler.log
StandardError=append:/var/log/ringmaster/scheduler.error.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable services
log_info "Enabling and starting services..."
systemctl daemon-reload
systemctl enable ringmaster-api.service
systemctl enable ringmaster-scheduler.service
systemctl start ringmaster-api.service
systemctl start ringmaster-scheduler.service

# Install ringmaster-cli
log_info "Installing ringmaster-cli..."
cat > /usr/local/bin/ringmaster-cli << 'EOF'
#!/bin/bash
# Ringmaster CLI - External Worker Interface

CONFIG_FILE="${CONFIG_FILE:-/etc/ringmaster/config.toml}"
API_URL="${API_URL:-http://localhost:8000}"

# Read config if exists
if [ -f "$CONFIG_FILE" ]; then
    API_URL=$(grep -m1 'api_url' "$CONFIG_FILE" | cut -d'"' -f2 || echo "$API_URL")
fi

case "$1" in
    pull-bead)
        # Pull a task for a worker
        WORKER_ID="$2"
        CAPABILITIES="$3"

        if [ -z "$WORKER_ID" ]; then
            echo "Error: --worker-id required" >&2
            exit 1
        fi

        RESPONSE=$(curl -s -X GET "$API_URL/api/workers/pull?worker_id=$WORKER_ID&capabilities=${CAPABILITIES:-[]}")
        echo "$RESPONSE"
        ;;

    build-prompt)
        # Build prompt for a task
        BEAD_ID="$2"
        OUTPUT="$3"

        if [ -z "$BEAD_ID" ]; then
            echo "Error: --bead-id required" >&2
            exit 1
        fi

        PROMPT=$(curl -s -X GET "$API_URL/api/workers/prompt/$BEAD_ID")

        if [ -n "$OUTPUT" ]; then
            echo "$PROMPT" > "$OUTPUT"
            echo "Prompt saved to $OUTPUT"
        else
            echo "$PROMPT"
        fi
        ;;

    report-result)
        # Report task completion result
        BEAD_ID="$2"
        STATUS="$3"
        EXIT_CODE="${4:-0}"
        OUTPUT="$4"

        if [ -z "$BEAD_ID" ] || [ -z "$STATUS" ]; then
            echo "Error: --bead-id and --status required" >&2
            exit 1
        fi

        curl -s -X POST "$API_URL/api/workers/result" \
            -H "Content-Type: application/json" \
            -d "{\"task_id\":\"$BEAD_ID\",\"status\":\"$STATUS\",\"exit_code\":$EXIT_CODE,\"output\":\"$OUTPUT\"}"
        echo
        ;;

    *)
        echo "Ringmaster CLI - External Worker Interface"
        echo ""
        echo "Usage: ringmaster-cli <command> [options]"
        echo ""
        echo "Commands:"
        echo "  pull-bead --worker-id <id> [--capabilities <json>]  Pull available task"
        echo "  build-prompt --bead-id <id> [--output <file>]       Build task prompt"
        echo "  report-result --bead-id <id> --status <status>      Report task result"
        echo "                [--exit-code <n>] [--output <text>]"
        echo ""
        echo "Environment variables:"
        echo "  API_URL      Ringmaster API URL (default: http://localhost:8000)"
        echo "  CONFIG_FILE  Config file path (default: /etc/ringmaster/config.toml)"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/ringmaster-cli

# Create config directory and default config
mkdir -p /etc/ringmaster
cat > /etc/ringmaster/config.toml << EOF
# Ringmaster Configuration

[api]
url = "http://localhost:8000"

[database]
path = "/opt/ringmaster/data/ringmaster.db"

[logging]
level = "info"
dir = "/var/log/ringmaster"

[projects]
dir = "/opt/ringmaster/projects"
EOF

# Setup backup cron job
log_info "Setting up backup automation..."
cat > /etc/cron.d/ringmaster-backup << 'EOF'
# Ringmaster Backup Automation
# Hourly backup with retention

0 * * * * root /opt/ringmaster/scripts/backup-ringmaster.sh hourly
0 0 * * * root /opt/ringmaster/scripts/backup-ringmaster.sh daily
EOF

# Create backup script if not exists
if [ ! -f "$INSTALL_DIR/scripts/backup-ringmaster.sh" ]; then
    log_warn "Backup script not found, creating placeholder"
    mkdir -p "$INSTALL_DIR/scripts"
    cat > "$INSTALL_DIR/scripts/backup-ringmaster.sh" << 'EOF'
#!/bin/bash
# Ringmaster Backup Script

BACKUP_DIR="/opt/ringmaster/backups"
DB_PATH="/opt/ringmaster/data/ringmaster.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

case "$1" in
    hourly)
        sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/ringmaster_hourly_${TIMESTAMP}.db"
        # Keep 7 days of hourly backups
        find "$BACKUP_DIR" -name "ringmaster_hourly_*" -mtime +7 -delete
        ;;
    daily)
        sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/ringmaster_daily_${TIMESTAMP}.db"
        # Keep 30 days of daily backups
        find "$BACKUP_DIR" -name "ringmaster_daily_*" -mtime +30 -delete
        ;;
    *)
        echo "Usage: $0 {hourly|daily}"
        exit 1
        ;;
esac
EOF
    chmod +x "$INSTALL_DIR/scripts/backup-ringmaster.sh"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/scripts/backup-ringmaster.sh"
fi

# Print completion message
echo ""
log_info "Ringmaster installation complete!"
echo ""
echo "Services:"
echo "  - API:       systemctl status ringmaster-api"
echo "  - Scheduler: systemctl status ringmaster-scheduler"
echo ""
echo "Access Ringmaster at:"
echo "  - Web UI:    http://localhost:8000"
echo "  - API:       http://localhost:8000/api"
echo "  - Health:    http://localhost:8000/api/health"
echo ""
echo "Logs:"
echo "  - API:       tail -f /var/log/ringmaster/api.log"
echo "  - Scheduler: tail -f /var/log/ringmaster/scheduler.log"
echo ""
echo "CLI:"
echo "  - ringmaster-cli --help"
echo ""
