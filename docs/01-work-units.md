# Work Units: Cards & Beads

## Overview

Ringmaster uses a hierarchy of work units inspired by [Steve Yegge's Beads](https://github.com/steveyegge/beads) system - a dependency-aware graph that replaces messy markdown plans with structured, persistent memory for coding agents.

## Unit Types

### Epic

Top-level container representing a feature, initiative, or significant body of work.

```
┌─────────────────────────────────────────────────────────┐
│  EPIC: bd-a3f8                                          │
│  "User Authentication System"                           │
│                                                         │
│  Contains: Tasks, context, acceptance criteria          │
│  Lifespan: Days to weeks                                │
│  Owner: Project (may span multiple workers)             │
└─────────────────────────────────────────────────────────┘
```

**Fields:**
- `id`: Hash-based ID (e.g., `bd-a3f8`) - prevents merge collisions
- `title`: Human-readable name
- `description`: Full context and requirements
- `priority`: P0-P4 (P0 = critical)
- `status`: draft | ready | in_progress | blocked | done
- `acceptance_criteria`: List of verifiable outcomes
- `context`: Enriched prompt context (RLM-processed)
- `children`: List of task IDs

### Task

Mid-level work item that a single worker can complete in one session.

```
┌─────────────────────────────────────────────────────────┐
│  TASK: bd-a3f8.1                                        │
│  "Implement JWT token generation"                       │
│                                                         │
│  Parent: bd-a3f8 (User Authentication System)           │
│  Lifespan: Hours to a day                               │
│  Owner: Single worker                                   │
└─────────────────────────────────────────────────────────┘
```

**Fields:**
- `id`: Hierarchical ID (e.g., `bd-a3f8.1`)
- `parent`: Epic ID
- `title`: Specific action
- `description`: Technical requirements
- `priority`: Inherited or overridden
- `status`: ready | assigned | in_progress | blocked | review | done | failed
- `dependencies`: List of task IDs that must complete first
- `dependents`: List of task IDs waiting on this
- `worker`: Assigned worker ID (when in_progress)
- `attempts`: Number of Ralph loop iterations
- `max_attempts`: Configurable ceiling before escalation
- `subtasks`: List of subtask IDs

### Subtask

Granular unit for complex tasks that need decomposition.

```
┌─────────────────────────────────────────────────────────┐
│  SUBTASK: bd-a3f8.1.1                                   │
│  "Add jsonwebtoken dependency to Cargo.toml"            │
│                                                         │
│  Parent: bd-a3f8.1 (JWT token generation)               │
│  Lifespan: Minutes to hours                             │
│  Owner: Single worker (same as parent task)             │
└─────────────────────────────────────────────────────────┘
```

**Fields:**
- Same as Task, but:
- `parent`: Task ID (not Epic)
- Typically stays with same worker as parent

### Decision

Special unit type for human-in-the-loop moments.

```
┌─────────────────────────────────────────────────────────┐
│  DECISION: bd-a3f8.1-d1                                 │
│  "Choose JWT library: jsonwebtoken vs jwt-simple"       │
│                                                         │
│  Blocks: bd-a3f8.1                                      │
│  Requires: Human input                                  │
│  Options: [A, B, C]                                     │
└─────────────────────────────────────────────────────────┘
```

**Fields:**
- `id`: Parent ID + `-d` + sequence
- `blocks`: Task ID waiting on this decision
- `question`: Clear question for human
- `context`: Summary of relevant information
- `options`: List of choices (if applicable)
- `recommendation`: Worker's suggested choice (if any)
- `resolution`: Human's answer (when resolved)
- `resolved_at`: Timestamp

### Question

Clarification request that doesn't necessarily block work.

```
┌─────────────────────────────────────────────────────────┐
│  QUESTION: bd-a3f8.1-q1                                 │
│  "Should tokens expire after 24h or 7 days?"            │
│                                                         │
│  Related: bd-a3f8.1                                     │
│  Urgency: low | medium | high                           │
└─────────────────────────────────────────────────────────┘
```

**Fields:**
- `id`: Parent ID + `-q` + sequence
- `related`: Task ID this relates to
- `question`: The clarification needed
- `urgency`: How soon answer is needed
- `default`: What worker will assume if no answer
- `answer`: Human's response (when provided)

## Status State Machine

```
                    ┌─────────┐
                    │  draft  │
                    └────┬────┘
                         │ enrich & validate
                         ▼
                    ┌─────────┐
          ┌─────────│  ready  │─────────┐
          │         └────┬────┘         │
          │              │ assign       │ dependencies
          │              ▼              │ not met
          │         ┌─────────┐         │
          │         │assigned │◄────────┘
          │         └────┬────┘
          │              │ worker picks up
          │              ▼
          │         ┌───────────┐
          │    ┌───►│in_progress│◄───┐
          │    │    └─────┬─────┘    │
          │    │          │          │
          │    │    ┌─────┴─────┐    │
          │    │    ▼           ▼    │
          │    │ ┌──────┐  ┌───────┐ │
          │    │ │review│  │blocked│ │ needs decision
          │    │ └──┬───┘  └───────┘ │
          │    │    │                │
          │    │    │ needs work     │
          │    └────┴────────────────┘
          │              │
          │         ┌────┴────┐
          │         ▼         ▼
          │    ┌──────┐  ┌────────┐
          └───►│ done │  │ failed │
               └──────┘  └────────┘
                              │
                              ▼ escalate
                         ┌─────────┐
                         │DECISION │
                         └─────────┘
```

## Storage Format

Following Beads convention: JSONL in `.ringmaster/` directory.

```
.ringmaster/
├── epics.jsonl        # All epics
├── tasks.jsonl        # All tasks
├── decisions.jsonl    # Pending and resolved decisions
├── questions.jsonl    # Pending and answered questions
└── history/           # Audit trail
    └── 2026-01-26.jsonl
```

**Example Task Record:**

```json
{
  "id": "bd-a3f8.1",
  "type": "task",
  "parent": "bd-a3f8",
  "title": "Implement JWT token generation",
  "description": "Create a JWT token generator using RS256...",
  "priority": "P1",
  "status": "in_progress",
  "dependencies": ["bd-a3f8.0"],
  "dependents": ["bd-a3f8.2", "bd-a3f8.3"],
  "worker": "claude-code-1",
  "attempts": 2,
  "max_attempts": 5,
  "created_at": "2026-01-26T10:00:00Z",
  "updated_at": "2026-01-26T14:30:00Z",
  "context_hash": "sha256:abc123..."
}
```

## Dependency Graph

Units form a directed acyclic graph (DAG):

```
         ┌─────────┐
         │ Epic A  │
         └────┬────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐
│Task 1 │ │Task 2 │ │Task 3 │
└───┬───┘ └───┬───┘ └───────┘
    │         │         ▲
    │         └─────────┤
    │                   │
    └───────────────────┘

Task 3 depends on Task 1 AND Task 2
Task 3 is "ready" only when both are "done"
```

## Integration with Beads CLI

Ringmaster can import/export standard Beads format for compatibility:

```bash
# Import existing beads project
ringmaster import --from-beads .beads/beads.jsonl

# Export for use with beads_viewer
ringmaster export --to-beads .beads/beads.jsonl
```

This allows using [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) for visualization and graph analysis while Ringmaster handles orchestration.
