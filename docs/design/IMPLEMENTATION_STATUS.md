# Ringmaster: Design vs Implementation Status

> Comparison of design document (Jan 28, 2026 conversation) vs current Python implementation

## Document Sources

| Document | Location | Description |
|----------|----------|-------------|
| Design Document | `ringmaster-design.md` | Comprehensive architecture from design conversation |
| Conversation | `ringmaster-conversation.md` | Raw transcript of design discussion |
| Implementation | `/home/coder/ringmaster/src/` | Current Python FastAPI codebase |

---

## Architecture Comparison

### High-Level Architecture

| Component | Design Spec | Implementation | Status |
|-----------|------------|----------------|--------|
| **Backend** | Hono (TS) or FastAPI | FastAPI ✅ | ✅ Match |
| **Database** | SQLite + Drizzle ORM | SQLite + aiosqlite | ⚠️ Different ORM |
| **Frontend** | SvelteKit or Next.js | React + Vite + Zustand | ⚠️ Different stack |
| **Real-time** | WebSocket | WebSocket ✅ | ✅ Match |
| **Worker Spawning** | Tmux/process | Tmux ✅ | ✅ Match |

---

## Feature Implementation Status

### ✅ Fully Implemented

| Feature | Design | Implementation |
|---------|--------|----------------|
| **Multimodal Input** | Text/audio/image ingestion | ✅ API endpoints accept text, file uploads |
| **Queue-Based Architecture** | Beads in backlog > workers | ✅ Priority queue with routing |
| **Heterogeneous Worker Pool** | Claude Code, OpenCode, Kilo, etc. | ✅ Worker types: claude-code, aider, generic |
| **Ralph Wiggum Loops** | Workers iterate until done | ✅ Workers poll and retry |
| **Human-in-the-Loop** | Decision/question inbox | ✅ Decisions API, questions with urgency |
| **Hot-Reload System** | 3-level reload (config/module/process) | ✅ File watcher + importlib.reload |
| **Git Worktree Isolation** | Per-task worktrees | ✅ Worktree manager |
| **Progress Monitoring** | Git-based signals + output patterns | ✅ Progress signals, outcome detection |
| **Web Dashboard** | Overview, metrics, health | ✅ React frontend with routes |
| **Project Abstraction** | Projects with context | ✅ Projects with tech stack, settings |

---

### ⚠️ Partially Implemented

| Feature | Design Spec | Current State | Gap |
|---------|------------|--------------|-----|
| **RLM Refinement** | RLM summarizes long chat + adds context | ⚠️ 9-layer enrichment exists, RLM integration unclear | RLM summarization of chat history |
| **Learning Scheduler** | ε-greedy → Thompson sampling | ⚠️ Random + memory bias only | No contextual bandit learning |
| **Worker Selection** | Learns (task_type, orchestrator, model) combos | ⚠️ Priority-based routing | No performance memory |
| **Project Inference** | Static analysis + RLM refinement | ⚠️ Manual project setup | No automatic inference |
| **Unstuck Handler** | Reassign to different worker + enhanced context | ⚠️ Basic retry logic | No smart reassignment |
| **Progress Signals** | Git + tests + time-based | ⚠️ Git-based only | Test delta tracking missing |
| **File Viewer** | Multi-format (PDF, media, data, .research.md) | ⚠️ Basic code/text viewer | No research notebook format |

---

### ❌ Not Implemented

| Feature | Design Spec | Notes |
|---------|------------|-------|
| **Shadow Testing** | Replay test corpus, compare outputs | Would enable safe self-upgrade |
| **Live Shadow** | Both versions on live traffic, compare | Advanced validation |
| **Canary Deployment** | 5% → 25% → 50% → 100% with rollback | Production-grade rollout |
| **Component Versioning** | Full lineage, interface contracts | For tracking hot-reload history |
| **Test Case Capture** | 1% sampling from production | For shadow testing corpus |
| **LLM-as-Judge** | Semantic comparison of stochastic outputs | For validation |
| **Research Notebook** | `.research.md` with sections, sources, citations | Specialized format |
| **File Annotations** | Comments on specific parts, conversations | Collaboration feature |
| **Multi-Format Export** | PDF, Word, Notion, GDocs | Research output |
| **Vector DB/RAG** | Memory for context injection | Current: file-based context |

---

## Bead/Task Schema Comparison

### Design Spec (TypeScript)

```typescript
interface Bead {
  id: string
  projectId: string
  prompt: string
  originalInput: { type: 'text'|'audio'|'image', raw: any }
  context: { files: string[], memory: string[], priorBeads: string[] }
  status: 'queued'|'assigned'|'working'|'blocked'|'review'|'done'|'failed'
  blockedOn?: 'human_decision'|'dependency'|'clarification'
  assignedWorker?: WorkerType
  attempts: AttemptLog[]
  workLog: string[]
  decisionsNeeded: Decision[]
}
```

### Implementation (Python)

```python
class Task(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    description: str
    status: TaskStatus  # backlog, ready, in_progress, blocked, review, done, failed
    blocked_on: Optional[str]
    assigned_worker_id: Optional[UUID]
    priority: Priority  # P0-P3
    bead_type: BeadType  # task, epic, decision, question
    # ... (matches design closely)
```

**Status**: ✅ Schema closely matches design spec

---

## Worker Pool Comparison

### Design Spec

```typescript
const workerPool: WorkerClass[] = [
  { orchestrator: 'claude-code', model: 'sonnet' },
  { orchestrator: 'claude-code', model: 'opus' },
  { orchestrator: 'opencode', model: 'gemini-2.5' },
  // ... more combinations
]
```

### Implementation

```python
# Worker types supported:
claude-code (sonnet, opus, glm-4.7)
aider (various models)
generic (any CLI tool)
```

**Status**: ✅ Heterogeneous workers implemented, design's learning selection not yet added

---

## Hot-Reload Comparison

### Design Spec: 3 Levels

1. **Config/Prompt Reload** - File watching, immediate effect
2. **Logic Module Reload** - Dynamic imports with cache busting
3. **Process Isolation** - Separate processes, supervisor handles upgrades

### Implementation

```python
# Level 1: ✅ Config reload
config_files = watch_config_files()

# Level 2: ✅ Module reload
importlib.reload(module)

# Level 3: ⚠️ Partial
# File watcher exists, but process isolation not implemented
```

**Status**: ⚠️ Level 1-2 working, Level 3 (process isolation) not implemented

---

## Validation Pipeline Comparison

### Design Spec: 4 Stages

```
PROPOSE → VALIDATE (static) → SHADOW (parallel) → LIVE SHADOW → CANARY → PROMOTE
```

### Implementation

```
Code change → Run tests → If pass: Hot-reload → If fail: Rollback
```

**Status**: ⚠️ Basic validation (tests), missing shadow testing and canary

---

## Tech Stack Differences

| Layer | Design Spec | Implementation | Notes |
|-------|------------|----------------|-------|
| **Frontend Framework** | SvelteKit or Next.js | React + Vite | Different, but functional |
| **Backend** | Hono (TS) or FastAPI | FastAPI | ✅ Match |
| **ORM** | Drizzle | aiosqlite (raw SQL) | Different, functional |
| **State Management** | Zustand or Jotai | Zustand | ✅ Match |
| **Real-time** | WebSocket | WebSocket | ✅ Match |
| **DnD** | dnd-kit | Not implemented | Kanban drag-drop missing |
| **Terminal** | xterm.js | Not implemented | Live logs in UI missing |
| **Charts** | Recharts/Chart.js | Not implemented | Metrics visualization missing |

---

## Key Architectural Decisions: Design vs Reality

### Decision 1: Python over TypeScript

**Design**: "Hono (TypeScript) or FastAPI"
**Reality**: FastAPI (Python) chosen

**Rationale**: Python enables true hot-reload via `importlib.reload()`, critical for self-improvement. TypeScript would require process restart.

---

### Decision 2: aiosqlite over Drizzle ORM

**Design**: "SQLite + Drizzle ORM"
**Reality**: aiosqlite with raw SQL

**Rationale**: Simpler, fewer dependencies. Migration system works well without ORM abstraction.

---

### Decision 3: React over SvelteKit/Next.js

**Design**: "SvelteKit or Next.js"
**Reality**: React + Vite + Zustand

**Rationale**: Familiarity, existing component ecosystem, Zustand for lightweight state management.

---

## What's Left to Build (Priority Order)

### Phase 1: Close Critical Gaps

1. **Learning Scheduler** - Replace random routing with contextual bandit
   - Track (task_type, worker, model) → outcome
   - Implement ε-greedy exploration
   - Graduate to Thompson sampling

2. **Project Auto-Inference** - Eliminate manual project setup
   - Static analysis: package.json, pyproject.toml, git log
   - RLM refinement for conventions
   - Automatic tech stack detection

3. **Smart Unstuck Handler** - Intelligently reassign failed tasks
   - Prefer different orchestrator, then different model
   - Enhanced prompt with failure context
   - Escalate after N attempts

### Phase 2: Advanced Validation

4. **Shadow Testing** - Safe self-upgrade
   - Test corpus capture from production
   - Replay on new component versions
   - Output comparison (exact + semantic)

5. **Component Versioning** - Track hot-reload lineage
   - Version each hot-swappable component
   - Interface contracts (schema, invariants)
   - Rollback history

### Phase 3: Production Polish

6. **Canary Deployment** - Gradual rollout
   - 5% → 25% → 50% → 100%
   - Auto-rollback on metrics regression
   - Live shadow mode

7. **Research Notebook** - `.research.md` format
   - Sections with progress tracking
   - Source citations with confidence
   - Multi-format export

8. **Frontend Enhancements**
   - Kanban drag-drop (dnd-kit)
   - Live terminal (xterm.js)
   - Metrics visualization (Recharts)

---

## Self-Hosting Capability

**Current Status**: ✅ **OPERATIONAL** (Iteration 27)

Ringmaster is already building itself using:
- Task queue for improvement work
- Workers pick up tasks via polling
- Hot-reload on test pass
- Worker-generated commits with proper attribution

**What enables self-hosting**:
- ✅ Hot-reload system (Python advantage)
- ✅ Worker spawning (tmux)
- ✅ Git worktree isolation
- ✅ Test validation as backpressure
- ✅ Human-in-the-loop for decisions

---

## Conclusion

The current Ringmaster implementation **closely follows the design document** for core functionality:

**Already Built (✅)**:
- Multimodal input → Queue → Worker pool → Progress monitoring
- Hot-reload, git worktrees, human-in-the-loop
- Web dashboard, project abstraction

**Partially Built (⚠️)**:
- Learning (exists but not sophisticated)
- Validation (tests pass/fail, no shadow testing)
- Project inference (manual, not automatic)

**Not Built (❌)**:
- Shadow testing, canary deployment
- Research notebook format
- Advanced file viewer

**Key Insight**: The design document was prescient. Most core features are implemented. What's missing is primarily **advanced validation** (shadow testing, canary) and **learning** (contextual bandit scheduler).

**Rust vs Python Question**: The design left tech stack open ("Hono or FastAPI"). Python was the right choice for **hot-reload**, which is the cornerstone of self-improvement. Rust would make this significantly harder.
