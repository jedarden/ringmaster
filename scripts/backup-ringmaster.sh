#!/bin/bash
# Ringmaster Backup Script
# Comprehensive backup with retention, compression, and verification

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/ringmaster/backups}"
DB_PATH="${RINGMASTER_DATABASE_PATH:-/opt/ringmaster/data/ringmaster.db}"
HOURLY_RETENTION_DAYS="${HOURLY_RETENTION_DAYS:-7}"
DAILY_RETENTION_DAYS="${DAILY_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${BACKUP_DIR}/backup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

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
    esac

    # Also log to file if directory exists
    if [ -d "$BACKUP_DIR" ]; then
        echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    fi
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
        if ! sqlite3 "$backup_file" "PRAGMA integrity_check;" | grep -q "ok"; then
            log ERROR "Backup file $backup_file failed SQLite integrity check"
            return 1
        fi
    fi

    log INFO "Backup verified: $backup_file"
    return 0
}

cleanup_old_backups() {
    local pattern=$1
    local retention_days=$2

    local count=$(find "$BACKUP_DIR" -name "$pattern" -mtime +$retention_days 2>/dev/null | wc -l)

    if [ "$count" -gt 0 ]; then
        log INFO "Removing $count backups older than $retention_days days matching $pattern"
        find "$BACKUP_DIR" -name "$pattern" -mtime +$retention_days -delete
    fi
}

compress_old_backups() {
    local pattern=$1
    local older_than_hours=$2

    # Find uncompressed backups older than specified hours and compress them
    find "$BACKUP_DIR" -name "$pattern" -mmin +$((older_than_hours * 60)) ! -name "*.gz" 2>/dev/null | while read -r file; do
        if [ -f "$file" ]; then
            log INFO "Compressing: $file"
            gzip "$file"
        fi
    done
}

do_backup() {
    local backup_type=$1
    local backup_filename

    # Ensure backup directory exists
    mkdir -p "$BACKUP_DIR"

    # Check if database exists
    if [ ! -f "$DB_PATH" ]; then
        log ERROR "Database not found at $DB_PATH"
        exit 1
    fi

    case "$backup_type" in
        hourly)
            backup_filename="ringmaster_hourly_${TIMESTAMP}.db"
            ;;
        daily)
            backup_filename="ringmaster_daily_${TIMESTAMP}.db"
            ;;
        manual)
            backup_filename="ringmaster_manual_${TIMESTAMP}.db"
            ;;
        *)
            log ERROR "Unknown backup type: $backup_type"
            echo "Usage: $0 {hourly|daily|manual}"
            exit 1
            ;;
    esac

    local backup_path="$BACKUP_DIR/$backup_filename"

    log INFO "Starting $backup_type backup to $backup_path"

    # Use SQLite's .backup command for a consistent backup
    # This creates a hot backup without locking the database
    if sqlite3 "$DB_PATH" ".backup '$backup_path'" 2>/dev/null; then
        log INFO "Backup created: $backup_path"
    else
        log ERROR "Failed to create backup"
        exit 1
    fi

    # Verify the backup
    if ! verify_backup "$backup_path"; then
        log ERROR "Backup verification failed, removing corrupt backup"
        rm -f "$backup_path"
        exit 1
    fi

    # Get backup size
    local size=$(du -h "$backup_path" | cut -f1)
    log INFO "Backup size: $size"

    # Cleanup based on backup type
    case "$backup_type" in
        hourly)
            # Clean up old hourly backups
            cleanup_old_backups "ringmaster_hourly_*" "$HOURLY_RETENTION_DAYS"
            # Compress hourly backups older than 24 hours
            compress_old_backups "ringmaster_hourly_*.db" 24
            ;;
        daily)
            # Clean up old daily backups
            cleanup_old_backups "ringmaster_daily_*" "$DAILY_RETENTION_DAYS"
            # Compress daily backups older than 7 days
            compress_old_backups "ringmaster_daily_*.db" $((7 * 24))
            ;;
        manual)
            # Manual backups don't auto-cleanup
            log INFO "Manual backup created (no automatic cleanup)"
            ;;
    esac

    log INFO "$backup_type backup completed successfully"

    # Print backup location
    echo "$backup_path"
}

list_backups() {
    echo "Available backups in $BACKUP_DIR:"
    echo ""

    if [ -d "$BACKUP_DIR" ]; then
        echo "=== Hourly Backups ==="
        ls -lh "$BACKUP_DIR"/ringmaster_hourly_* 2>/dev/null || echo "  (none)"
        echo ""

        echo "=== Daily Backups ==="
        ls -lh "$BACKUP_DIR"/ringmaster_daily_* 2>/dev/null || echo "  (none)"
        echo ""

        echo "=== Manual Backups ==="
        ls -lh "$BACKUP_DIR"/ringmaster_manual_* 2>/dev/null || echo "  (none)"
    else
        echo "Backup directory does not exist: $BACKUP_DIR"
    fi
}

show_help() {
    echo "Ringmaster Backup Script"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  hourly    Create an hourly backup (retains $HOURLY_RETENTION_DAYS days)"
    echo "  daily     Create a daily backup (retains $DAILY_RETENTION_DAYS days)"
    echo "  manual    Create a manual backup (no automatic cleanup)"
    echo "  list      List all available backups"
    echo "  verify    Verify a specific backup file"
    echo "  help      Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  BACKUP_DIR                Backup directory (default: /opt/ringmaster/backups)"
    echo "  RINGMASTER_DATABASE_PATH  Database path (default: /opt/ringmaster/data/ringmaster.db)"
    echo "  HOURLY_RETENTION_DAYS     Days to keep hourly backups (default: 7)"
    echo "  DAILY_RETENTION_DAYS      Days to keep daily backups (default: 30)"
    echo ""
    echo "Examples:"
    echo "  $0 hourly                 # Create hourly backup"
    echo "  $0 daily                  # Create daily backup"
    echo "  $0 manual                 # Create manual backup"
    echo "  $0 list                   # List all backups"
    echo "  $0 verify /path/to/backup.db  # Verify a backup"
}

# Main
case "${1:-help}" in
    hourly|daily|manual)
        do_backup "$1"
        ;;
    list)
        list_backups
        ;;
    verify)
        if [ -z "${2:-}" ]; then
            log ERROR "Verify requires a backup file path"
            exit 1
        fi
        verify_backup "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log ERROR "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
