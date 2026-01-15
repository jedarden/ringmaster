# ADR-001: Single Rust Binary

## Status

Accepted

## Context

Ringmaster needs to run inside a Coder development environment, serving a web UI while also providing terminal output for event logging. We need to choose a deployment model.

Options considered:
- Multi-container microservices
- Single binary with embedded assets
- Electron-style desktop app

## Decision

Build Ringmaster as a single Rust binary that:
- Embeds the React frontend via `rust-embed`
- Serves HTTP/WebSocket via Axum
- Uses SQLite for persistence
- Outputs events to terminal

## Consequences

**Easier:**
- Deployment: single binary, no container orchestration
- Development: cargo build produces complete artifact
- Operations: no inter-service communication complexity

**Harder:**
- Scaling: single instance only (acceptable for dev environment)
- Updates: must rebuild entire binary for any change
