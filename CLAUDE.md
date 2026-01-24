# Ringmaster Development

## Project Overview

Ringmaster is an SDLC orchestration platform built as a single Rust binary with embedded React frontend. It runs inside a user's codespace (GitHub Codespaces, devcontainers) where the codespace provides the security boundary.

## Tech Stack

- **Backend**: Rust, Axum, SQLx, SQLite
- **Frontend**: React, TypeScript, Vite, Tailwind
- **Embedding**: rust-embed for static assets
- **Coding Platform**: Claude Code CLI (auto-installed)

## Architecture

- Heuristic-based orchestration (no LLM for internal decisions)
- RLM summarization for long context
- Multi-platform coding agent support via CLI execution
- Auto-installation of Claude Code CLI on first run

## Key Directories

```
ringmaster/
├── src/
│   ├── platforms/      # Coding platform abstraction
│   │   ├── mod.rs      # CodingPlatform trait
│   │   ├── claude_code.rs  # Claude Code CLI implementation
│   │   ├── installer.rs    # Auto-installation logic
│   │   └── stream_parser.rs
│   ├── loops/          # Ralph-Wiggum loop manager
│   ├── state_machine/  # Card lifecycle (16 states)
│   └── ...
├── frontend/           # React app
├── docs/               # Architecture documentation
├── docs/adr/           # Architecture Decision Records
└── migrations/         # SQLite migrations
```

## Development Commands

```bash
# Build
cargo build --release

# Run (auto-installs Claude Code CLI if missing)
./target/release/ringmaster

# Check dependencies
./target/release/ringmaster doctor

# Install Claude Code CLI manually
./target/release/ringmaster doctor --install

# Show configuration
./target/release/ringmaster config

# Run with custom port
./target/release/ringmaster --port 3000

# Frontend dev (hot reload)
cd frontend && npm run dev

# Run tests
cargo test
```

## Claude Code CLI

Ringmaster requires Claude Code CLI for autonomous coding loops. It auto-installs on startup if not found.

**Manual installation:**
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Verify:**
```bash
claude --version
```

## ADRs

Check `docs/adr/` before making architectural changes.

- ADR-001: Single Rust binary with embedded frontend
- ADR-002: Heuristic orchestration (no LLM for decisions)
- ADR-003: Multi-platform support via CLI execution + auto-installation
