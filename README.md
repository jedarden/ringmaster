# Ringmaster

SDLC orchestration platform that coordinates AI coding agents through the complete software development lifecycle.

## Quick Start

```bash
# Build
cargo build --release

# Check dependencies (auto-installs Claude Code CLI if missing)
./target/release/ringmaster doctor --install

# Run
./target/release/ringmaster
```

Open http://localhost:8080 in your browser.

### Requirements

- **Rust 1.70+** for building
- **Claude Code CLI** for coding loops (auto-installed on first run)
- **Git** for worktree management

### CLI Commands

```bash
ringmaster                    # Start server (default: localhost:8080)
ringmaster --port 3000        # Custom port
ringmaster config             # Show configuration
ringmaster doctor             # Check dependencies
ringmaster doctor --install   # Install missing dependencies
```

## Overview

Ringmaster combines Kanban-style task management with autonomous coding loops, managing cards from code generation through build and deployment.

```
Create Card → Add Context → Run Loop → Build → Deploy → Done
                 ↑              │
                 └── Intervene ←┘
```

## Core Concepts

- **Cards**: Units of work progressing through SDLC stages
- **Loops**: Iterative AI coding sessions (Ralph-Wiggum pattern)
- **Platforms**: Coding CLIs (Claude Code, Aider, etc.)
- **RLM**: Context summarization for long histories

## Key Controls

| Lever | Options |
|-------|---------|
| **Execution** | Run / Pause / Stop |
| **Platform** | Claude Code, Aider, Codex, Custom |
| **Model** | Opus, Sonnet, Haiku, GPT-4, etc. |
| **Config** | Repo with CLAUDE.md, skills/, patterns.json |
| **Limits** | Iterations, Cost, Time |
| **Context** | Notes, Files, History |
| **Intervention** | Approve, Edit, Skip, Hint |

## Architecture

- **Orchestration**: Heuristic-based (state machine, loop control)
- **Context Curation**: RLM summarization when content exceeds limits
- **Code Generation**: External LLM via chosen platform

See [docs/00-architecture-overview.md](docs/00-architecture-overview.md) for details.

## Documentation

- [Architecture Overview](docs/00-architecture-overview.md)
- [State Machine](docs/01-state-machine.md)
- [Prompt Pipeline](docs/02-prompt-pipeline.md)
- [Loop Manager](docs/03-loop-manager.md)
- [Integrations](docs/04-integrations.md)
- [UX Controls](docs/10-ux-controls.md)

## ADRs

Architecture Decision Records in [docs/adr/](docs/adr/).

## License

MIT
