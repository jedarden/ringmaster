#!/bin/bash
# Ringmaster Restore Script
# Restore database from backup with safety checks

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/ringmaster/backups}"
DB_PATH="${RINGMASTER_DATABASE_PATH:-/opt/ringmaster/data/ringmaster.db}"
DB_DIR=$(dirname "$DB_PATH")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    local level=$1
    shift
    local message="$*"

    case "$level" in
        INFO)
            echo -e "${GREEN}[INFO]${NC} $message"
            ;;
        WARN)
            echo -e "${YELLOW}[WARN]${NC} $message"
            ;;
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
        STEP)
            echo -e "${BLUE}[STEP]${NC} $message"
            ;;
    esac
}

verify_backup() {
    local backup_file=$1

    # Check file exists and has size > 0
    if [ ! -f "$backup_file" ] || [ ! -s "$backup_file" ]; then
        log ERROR "Backup file $backup_file is missing or empty"
        return 1
    fi

    # For compressed files, verify gzip integrity
    if [[ "$backup_file" == *.gz ]]; then
        if ! gzip -t "$backup_file" 2>/dev/null; then
            log ERROR "Backup file $backup_file failed gzip integrity check"
            return 1
        fi
    fi

    # For uncompressed SQLite files, verify database integrity
    if [[ "$backup_file" == *.db ]]; then
        if ! sqlite3 "$backup_file" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
            log ERROR "Backup file $backup_file failed SQLite integrity check"
            return 1
        fi
    fi

    log INFO "Backup verified: $backup_file"
    return 0
}

stop_services() {
    log STEP "Stopping Ringmaster services..."

    # Try systemctl first
    if command -v systemctl &>/dev/null; then
        systemctl stop ringmaster-api.service 2>/dev/null || true
        systemctl stop ringmaster-scheduler.service 2>/dev/null || true
    fi

    # Wait for any lingering connections
    sleep 2
}

start_services() {
    log STEP "Starting Ringmaster services..."

    if command -v systemctl &>/dev/null; then
        systemctl start ringmaster-api.service 2>/dev/null || true
        systemctl start ringmaster-scheduler.service 2>/dev/null || true
    fi
}

do_restore() {
    local backup_file=$1
    local force=${2:-false}
    local temp_file=""

    # Check if backup file is provided
    if [ -z "$backup_file" ]; then
        log ERROR "Backup file path is required"
        show_help
        exit 1
    fi

    # Resolve relative paths
    if [[ "$backup_file" != /* ]]; then
        # Check in backup directory first
        if [ -f "$BACKUP_DIR/$backup_file" ]; then
            backup_file="$BACKUP_DIR/$backup_file"
        elif [ -f "$backup_file" ]; then
            backup_file="$(pwd)/$backup_file"
        fi
    fi

    # Check if backup exists
    if [ ! -f "$backup_file" ]; then
        log ERROR "Backup file not found: $backup_file"
        exit 1
    fi

    log INFO "Restoring from: $backup_file"

    # Verify the backup before proceeding
    if ! verify_backup "$backup_file"; then
        log ERROR "Backup verification failed. Aborting restore."
        exit 1
    fi

    # Decompress if necessary
    if [[ "$backup_file" == *.gz ]]; then
        log STEP "Decompressing backup..."
        temp_file="/tmp/ringmaster_restore_${TIMESTAMP}.db"
        gunzip -c "$backup_file" > "$temp_file"
        backup_file="$temp_file"
    fi

    # Show current database stats
    if [ -f "$DB_PATH" ]; then
        local current_size=$(du -h "$DB_PATH" | cut -f1)
        local current_tables=$(sqlite3 "$DB_PATH" ".tables" 2>/dev/null | wc -w || echo "0")
        log INFO "Current database: $current_size, $current_tables tables"
    else
        log WARN "No existing database at $DB_PATH"
    fi

    # Show backup stats
    local backup_size=$(du -h "$backup_file" | cut -f1)
    local backup_tables=$(sqlite3 "$backup_file" ".tables" 2>/dev/null | wc -w || echo "0")
    log INFO "Backup database: $backup_size, $backup_tables tables"

    # Confirmation prompt (skip if force flag)
    if [ "$force" != "true" ]; then
        echo ""
        echo -e "${YELLOW}WARNING: This will replace the current database!${NC}"
        echo ""
        read -p "Are you sure you want to restore? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log INFO "Restore cancelled by user"
            [ -n "$temp_file" ] && rm -f "$temp_file"
            exit 0
        fi
    fi

    # Stop services
    stop_services

    # Create safety backup of current database
    if [ -f "$DB_PATH" ]; then
        local safety_backup="$BACKUP_DIR/pre_restore_${TIMESTAMP}.db"
        log STEP "Creating safety backup: $safety_backup"
        mkdir -p "$BACKUP_DIR"
        cp "$DB_PATH" "$safety_backup"
    fi

    # Ensure database directory exists
    mkdir -p "$DB_DIR"

    # Perform the restore
    log STEP "Restoring database..."
    cp "$backup_file" "$DB_PATH"

    # Verify restored database
    if sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
        log INFO "Database integrity verified after restore"
    else
        log ERROR "Restored database failed integrity check!"
        log ERROR "Attempting to restore from safety backup..."
        if [ -f "$safety_backup" ]; then
            cp "$safety_backup" "$DB_PATH"
            log INFO "Reverted to safety backup"
        fi
        start_services
        exit 1
    fi

    # Clean up temp file
    [ -n "$temp_file" ] && rm -f "$temp_file"

    # Start services
    start_services

    # Final stats
    local restored_size=$(du -h "$DB_PATH" | cut -f1)
    local restored_tables=$(sqlite3 "$DB_PATH" ".tables" 2>/dev/null | wc -w || echo "0")

    echo ""
    log INFO "Restore completed successfully!"
    echo ""
    echo "Database stats:"
    echo "  Path:   $DB_PATH"
    echo "  Size:   $restored_size"
    echo "  Tables: $restored_tables"
    echo ""
    if [ -f "${safety_backup:-}" ]; then
        echo "Safety backup saved at: $safety_backup"
    fi
}

list_backups() {
    echo "Available backups in $BACKUP_DIR:"
    echo ""

    if [ -d "$BACKUP_DIR" ]; then
        # Sort by modification time, newest first
        echo "Recent backups (newest first):"
        echo ""
        ls -lt "$BACKUP_DIR"/ringmaster_*.{db,db.gz} 2>/dev/null | head -20 || echo "  (no backups found)"
    else
        echo "Backup directory does not exist: $BACKUP_DIR"
    fi
}

show_help() {
    echo "Ringmaster Restore Script"
    echo ""
    echo "Usage: $0 <backup-file> [--force]"
    echo "       $0 list"
    echo "       $0 help"
    echo ""
    echo "Commands:"
    echo "  <backup-file>  Path to backup file to restore"
    echo "  list           List available backups"
    echo "  help           Show this help message"
    echo ""
    echo "Options:"
    echo "  --force        Skip confirmation prompt"
    echo ""
    echo "Environment variables:"
    echo "  BACKUP_DIR                Backup directory (default: /opt/ringmaster/backups)"
    echo "  RINGMASTER_DATABASE_PATH  Database path (default: /opt/ringmaster/data/ringmaster.db)"
    echo ""
    echo "Examples:"
    echo "  $0 ringmaster_daily_20240115_000001.db"
    echo "  $0 /opt/ringmaster/backups/ringmaster_hourly_20240115_120000.db.gz"
    echo "  $0 ringmaster_manual_20240115_143000.db --force"
    echo "  $0 list"
    echo ""
    echo "Notes:"
    echo "  - Compressed backups (.gz) are automatically decompressed"
    echo "  - A safety backup is created before restore"
    echo "  - Services are automatically stopped and restarted"
}

# Main
case "${1:-help}" in
    list)
        list_backups
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        # Assume it's a backup file path
        force="false"
        if [ "${2:-}" = "--force" ] || [ "${2:-}" = "-f" ]; then
            force="true"
        fi
        do_restore "$1" "$force"
        ;;
esac
