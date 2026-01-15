# Ringmaster

SDLC orchestration platform that coordinates AI coding agents through the complete software development lifecycle.

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
