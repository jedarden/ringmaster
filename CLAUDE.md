# Ringmaster Development

## Project Overview

Ringmaster is an SDLC orchestration platform built as a single Rust binary with embedded React frontend.

## Tech Stack

- **Backend**: Rust, Axum, SQLx, SQLite
- **Frontend**: React, TypeScript, Vite, Tailwind
- **Embedding**: rust-embed for static assets

## Architecture

- Heuristic-based orchestration (no LLM for internal decisions)
- RLM summarization for long context
- Multi-platform coding agent support

## Key Directories

```
ringmaster/
├── docs/           # Architecture documentation
├── docs/adr/       # Architecture Decision Records
├── prompts/        # Marathon coding prompts
├── crates/         # Rust workspace (to be created)
└── frontend/       # React app (to be created)
```

## Development Commands

```bash
# Build
cargo build --release

# Run
./target/release/ringmaster

# Frontend dev
cd frontend && npm run dev
```

## ADRs

Check `docs/adr/` before making architectural changes.
