#!/bin/bash
# Start Ringmaster backend for E2E tests
# This script initializes the database (if needed) and starts the API server

set -e

cd "$(dirname "$0")/.."

# Initialize database if it doesn't exist
if [ ! -f ~/.ringmaster/ringmaster.db ]; then
  echo "Initializing Ringmaster database..."
  python3 -m ringmaster.cli init
else
  echo "Database already exists, skipping init"
fi

# Start the API server
echo "Starting Ringmaster API server on port 8000..."
exec python3 -m ringmaster.cli serve --port 8000
