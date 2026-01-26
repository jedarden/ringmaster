# Ringmaster

**Multi-Coding-Agent Orchestration Platform**

*Like a circus ringmaster controlling the chaos of different acts*

## Vision

LLM coding orchestrators today are chaotic - each tool (Claude Code, Codex CLI, Kilo Code, Codebuff, Goose, etc.) operates independently with its own paradigms. Ringmaster brings order to the circus, providing a unified orchestration layer that:

1. **Accepts multimedia input** (text, audio, images, screenshots)
2. **Enriches prompts** with RLM summarization + project context
3. **Queues work** as kanban cards / beads
4. **Dispatches to heterogeneous workers** from a shared pool
5. **Loops until done** (Ralph Wiggum style iterations)
6. **Surfaces decisions** back to the user when needed

## Core Concepts

### Projects as First-Class Citizens

Users define **projects** - not just tasks. A project carries:
- Description and goals
- Chat history (RLM-summarized when long)
- Supplemental context (ADRs, libraries, conventions)
- Active work items (cards/beads)

### Prompt Enrichment Pipeline

```
User Input (text/audio/image)
        │
        ▼
┌─────────────────────────┐
│  Parse & Transcribe     │  ← Multimedia → Text
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  RLM Summarization      │  ← Condense long context
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  Context Injection      │  ← Project context, ADRs, libs
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  Card/Bead Creation     │  ← Structured work unit
└─────────────────────────┘
```

### Work Units: Cards & Beads

Inspired by Steve Yegge's "beads" concept - small, well-defined units of work that:
- Have clear acceptance criteria
- Can be processed independently
- Chain together for larger features
- Track their own state and history

### Heterogeneous Worker Pool

Ringmaster doesn't care *which* LLM tool does the work. It maintains a pool of workers:

| Worker Type | Interface | Strengths |
|-------------|-----------|-----------|
| Claude Code (headless) | CLI | Strong reasoning, tool use |
| Codex CLI | CLI | Fast iteration, GPT-5 |
| Kilo Code | CLI | Local/private, customizable |
| Codebuff | CLI | Lightweight, fast |
| Goose | CLI | Extensible, plugins |
| *Others* | CLI/API | As ecosystem grows |

Workers pull from the queue when free. Work items > workers = healthy backlog.

### Ralph Wiggum Loops

Each worker runs iterative loops on their assigned card:

```
┌─────────────────────────────────────────┐
│  RALPH LOOP                             │
│                                         │
│  while (!done && iterations < max) {    │
│    1. Attempt implementation            │
│    2. Run validation (tests, lint)      │
│    3. If pass → done                    │
│    4. If fail → analyze, retry          │
│  }                                      │
│                                         │
│  if (!done) → escalate to human         │
└─────────────────────────────────────────┘
```

Named after the pattern of "keep trying until it works or give up" - simple but effective for autonomous coding.

### Human-in-the-Loop

When a worker:
- Hits max iterations without success
- Encounters an ambiguous requirement
- Needs a decision between alternatives
- Completes significant work

...Ringmaster surfaces this to the user with:
- **Summary** of what was attempted/accomplished
- **Context** needed to make the decision
- **Options** if applicable

The user responds, and work continues.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           RINGMASTER                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  INGESTION LAYER                                              │   │
│  │  • REST API / WebSocket                                       │   │
│  │  • Multimedia handling (speech-to-text, image description)    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  ENRICHMENT ENGINE                                            │   │
│  │  • RLM summarization                                          │   │
│  │  • Project context injection                                  │   │
│  │  • Card/bead structuring                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  WORK QUEUE                                                   │   │
│  │  • Priority ordering                                          │   │
│  │  • Dependency tracking                                        │   │
│  │  • Backlog management                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  WORKER POOL                                                  │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐             │   │
│  │  │ Claude  │ │  Codex  │ │  Kilo   │ │  Goose  │  ...        │   │
│  │  │  Code   │ │   CLI   │ │  Code   │ │         │             │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘             │   │
│  │       └───────────┴───────────┴───────────┘                  │   │
│  │                    │                                          │   │
│  │              Ralph Loops                                      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  HUMAN INTERFACE                                              │   │
│  │  • Decision requests                                          │   │
│  │  • Progress summaries                                         │   │
│  │  • Completion notifications                                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Differentiators

1. **Heterogeneous workers** - Not locked to one LLM/tool
2. **Project-centric** - Context persists across work items
3. **Queue-first** - Designed for backlog > workers
4. **Multimedia input** - Voice, images, text all welcome
5. **Human-in-the-loop** - Escalation with rich context
6. **Self-improving** - Hot-reloadable, can improve itself (flywheel effect)

## Documentation

| Document | Description |
|----------|-------------|
| [01-work-units.md](docs/01-work-units.md) | Cards, beads, epics, tasks, decisions - work unit types and schemas |
| [02-worker-interface.md](docs/02-worker-interface.md) | CLI-based worker abstraction (text in, text out) |
| [03-prioritization.md](docs/03-prioritization.md) | PageRank + dependency analysis for task ordering |
| [04-context-enrichment.md](docs/04-context-enrichment.md) | Source-based context assembly (conversation, research, code, logs, etc.) |
| [05-state-persistence.md](docs/05-state-persistence.md) | SQLite + files for state management |
| [06-deployment.md](docs/06-deployment.md) | Hot-reloadable architecture for self-improvement |
| [07-user-experience.md](docs/07-user-experience.md) | Mailbox UX, file preview, agents dashboard, reversibility |
| [08-open-architecture.md](docs/08-open-architecture.md) | Resolved design decisions: git worktrees, validation, routing, security |
| [09-remaining-decisions.md](docs/09-remaining-decisions.md) | Bead lifecycle, worker spawning, output parsing, operations |

## References

- [beads](https://github.com/steveyegge/beads) - Steve Yegge's task management system
- [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) - Graph analytics for beads (PageRank, betweenness, HITS)
- [@doodlestein](https://x.com/doodlestein) - Jeffrey Emanuel's work on beads prioritization

## Status

Design phase. Core architecture documented.
