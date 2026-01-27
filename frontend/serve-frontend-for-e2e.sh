#!/bin/bash
# Start Ringmaster frontend for E2E tests using production build
# This script builds the frontend and serves it using the stable 'serve' package
# instead of the unstable 'vite preview' server which crashes under test load

set -e

cd "$(dirname "$0")"

# Build frontend with production API URL
# Note: VITE_API_URL must include /api path since client code uses it directly
echo "Building Ringmaster frontend for E2E tests..."
export VITE_API_URL=http://localhost:8000/api
npm run build

# Serve production build using 'serve' package (stable)
echo "Serving frontend on http://localhost:4173..."
# Using port 4173 instead of 5173 to distinguish production from dev mode
# -s flag for single-page app mode, -l flag to specify port
exec npx serve dist -s -l 4173
