# Ringmaster Design Documents

Design documentation for Ringmaster, an LLM coding agent orchestrator.

## Files

| File | Description |
|------|-------------|
| `ringmaster-design.md` | Comprehensive design document with architecture, components, and UX specifications |
| `ringmaster-conversation.md` | Raw conversation transcript that generated the design |

## Quick Start

The design document covers:

1. **Architecture** - Core components and data flow
2. **Bead Abstraction** - Unit of work definition
3. **Worker Pool** - Heterogeneous agent management
4. **Learning Scheduler** - Contextual bandit for worker selection
5. **Progress Monitoring** - Stuck detection and recovery
6. **Hot-Reload System** - Self-improvement capability
7. **Validation Pipeline** - Shadow testing and canary deployment
8. **Web UX** - Dashboard, queue, decisions inbox
9. **File Viewer** - Research notebook and artifact management

## Key Concepts

### The Name
"Ringmaster" - conducting chaos (multiple AI agents) like different acts of a circus.

### Core Loop
```
User Input → RLM Refinement → Bead Queue → Worker Pool → Progress Monitor → Summary
```

### Worker Pool
Heterogeneous mix of:
- Claude Code (Sonnet, Opus, GLM-4.7)
- OpenCode (Gemini, GPT-4o)
- Kilo Code
- Codebuff
- Goose (local models)

### Learning
The scheduler learns which (task_type, orchestrator, model) combinations work best using ε-greedy exploration → Thompson sampling.

## Tech Stack (Proposed)

- **Frontend**: SvelteKit or Next.js + Tailwind + shadcn/ui
- **Backend**: Hono (TypeScript) or FastAPI
- **Database**: SQLite + Drizzle ORM
- **Real-time**: WebSocket

## Status

Design phase. See `ringmaster-design.md` for full specification.

## License

TBD
