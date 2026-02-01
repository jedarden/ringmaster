# Ringmaster: LLM Coding Agent Orchestrator

> Design document compiled from conversation on January 28, 2026

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Bead Abstraction](#bead-abstraction)
5. [Worker Pool](#worker-pool)
6. [Scheduling & Learning](#scheduling--learning)
7. [Progress Monitoring & Unstuck Handling](#progress-monitoring--unstuck-handling)
8. [Project Inference](#project-inference)
9. [Hot-Reload System](#hot-reload-system)
10. [Validation & Rollback Pipeline](#validation--rollback-pipeline)
11. [Web UX](#web-ux)
12. [File Viewer](#file-viewer)
13. [Tech Stack](#tech-stack)

---

## Overview

Ringmaster is a natural language orchestrator for LLM coding agents. The name reflects its role: conducting chaos (multiple AI agents) like different acts of a circus.

### Core Concept

```
User Input (text/audio/image)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         RINGMASTER                                   │
│                                                                      │
│  1. INGEST      - Multimodal input processing                       │
│  2. REFINE      - RLM enhances prompt + adds context                │
│  3. QUEUE       - Beads (work units) in backlog                     │
│  4. DISPATCH    - N agents pick up work as they become free         │
│  5. MONITOR     - Progress tracking, stuck detection                │
│  6. SUMMARIZE   - Results + git changes → human-readable summary    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Goals

- **Queue-based**: More work units than available workers (backlog)
- **Heterogeneous workers**: Claude Code, OpenCode, Kilo, Codebuff, Goose, etc.
- **Learning scheduler**: Discovers which orchestrator+model combos work best
- **Human-in-the-loop**: Surface decisions and summaries to user
- **Self-improving**: Components can hot-reload and upgrade themselves

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              WEB UI                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │  Projects   │  │   Beads     │  │  Decisions  │  │   Activity    │  │
│  │  (config)   │  │  (kanban)   │  │   (inbox)   │  │   (stream)    │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ WebSocket
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           RINGMASTER CORE                                │
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │     INGEST       │    │     REFINER      │    │    SCHEDULER     │  │
│  │                  │    │                  │    │                  │  │
│  │ • Multimodal     │───▶│ • RLM expand     │───▶│ • Random + ε     │  │
│  │ • Whisper/Vision │    │ • Context inject │    │ • Memory bias    │  │
│  │ • Project detect │    │ • Decompose      │    │ • Capability fit │  │
│  └──────────────────┘    └──────────────────┘    └────────┬─────────┘  │
│                                                           │             │
│  ┌────────────────────────────────────────────────────────┼──────────┐ │
│  │                      WORKER POOL                       │          │ │
│  │                                                        ▼          │ │
│  │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │ │
│  │   │Claude CC│ │OpenCode │ │  Kilo   │ │Codebuff │ │  Goose  │   │ │
│  │   │ Sonnet  │ │ Gemini  │ │ Claude  │ │  GPT-4  │ │  Local  │   │ │
│  │   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │ │
│  │        │           │           │           │           │        │ │
│  │        └───────────┴───────────┴───────────┴───────────┘        │ │
│  │                                │                                 │ │
│  │                         ┌──────┴──────┐                         │ │
│  │                         │  PROGRESS   │                         │ │
│  │                         │  MONITOR    │                         │ │
│  │                         └──────┬──────┘                         │ │
│  │                                │                                 │ │
│  │                    ┌───────────┴───────────┐                    │ │
│  │                    ▼                       ▼                    │ │
│  │             ┌─────────────┐        ┌─────────────┐              │ │
│  │             │   UNSTUCK   │        │  COMPLETE   │              │ │
│  │             │    AGENT    │        │  → SUMMARY  │              │ │
│  │             └─────────────┘        └─────────────┘              │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                         MEMORY                                   │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐│ │
│  │  │ SQLite   │  │  Git     │  │  Vector  │  │  Performance     ││ │
│  │  │ (beads)  │  │ (commits)│  │  (RAG)   │  │  (task→worker)   ││ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘│ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### Component Testability Spectrum

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    COMPONENT TESTABILITY SPECTRUM                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  DETERMINISTIC                                              STOCHASTIC  │
│  (easy to test)                                        (needs shadow)   │
│                                                                          │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤   │
│  │          │          │          │          │          │          │   │
│  │  Worker  │ Progress │ Scheduler│ Project  │ Unstuck  │ Refiner  │   │
│  │  Config  │ Monitor  │  Logic   │ Inference│  Logic   │ Prompts  │   │
│  │          │          │          │          │          │          │   │
│  │  Unit    │  Unit    │  Unit +  │  Shadow  │  Shadow  │  Shadow  │   │
│  │  Tests   │  Tests   │  Replay  │  + Eval  │  + Eval  │  + Eval  │   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Bead Abstraction

A "bead" is the unit of work, inspired by Steve Yegge's bead-on-a-string model. Beads can split, block, merge, and loop.

```typescript
interface Bead {
  id: string
  projectId: string
  
  // The refined prompt (post-RLM)
  prompt: string
  originalInput: {
    type: 'text' | 'audio' | 'image' | 'mixed'
    raw: any
  }
  
  // Injected context
  context: {
    files: string[]
    memory: string[]  // RAG hits
    priorBeads: string[]  // dependency chain
  }
  
  // State machine
  status: 'queued' | 'assigned' | 'working' | 'blocked' | 'review' | 'done' | 'failed'
  blockedOn?: 'human_decision' | 'dependency' | 'clarification'
  
  // Worker assignment
  assignedWorker?: WorkerType
  attempts: AttemptLog[]
  
  // For summarization
  workLog: string[]
  decisionsNeeded: Decision[]
}
```

### Bead Lifecycle

```
         ┌────────────────────────────────────┐
         │                                    │
         ▼                                    │
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   BACKLOG    │──▶│   QUEUED     │──▶│   WORKING    │
└──────────────┘   └──────────────┘   └──────┬───────┘
                                             │
                   ┌─────────────────────────┼─────────────────────────┐
                   │                         │                         │
                   ▼                         ▼                         ▼
            ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
            │   BLOCKED    │         │    STUCK     │         │   REVIEW     │
            │  (decision)  │         │  (reassign)  │         │  (approval)  │
            └──────────────┘         └──────────────┘         └──────┬───────┘
                   │                         │                         │
                   │                         │                         │
                   └─────────────────────────┴─────────────────────────┘
                                             │
                                             ▼
                                      ┌──────────────┐
                                      │     DONE     │
                                      └──────────────┘
```

---

## Worker Pool

### Worker Class Definition

```typescript
interface WorkerClass {
  orchestrator: 'claude-code' | 'opencode' | 'kilo' | 'codebuff' | 'goose'
  model: string  // 'sonnet', 'opus', 'gemini-2.5', 'gpt-4o', 'glm-4.7', etc.
}

// The pool is all combinations
const workerPool: WorkerClass[] = [
  { orchestrator: 'claude-code', model: 'sonnet' },
  { orchestrator: 'claude-code', model: 'opus' },
  { orchestrator: 'claude-code', model: 'glm-4.7' },
  { orchestrator: 'opencode', model: 'gemini-2.5' },
  { orchestrator: 'opencode', model: 'gpt-4o' },
  { orchestrator: 'kilo', model: 'sonnet' },
  { orchestrator: 'goose', model: 'local-qwen' },
  // etc
]
```

### Worker Adapter Approaches

#### Option A: Clean Abstractions

```typescript
interface WorkerAdapter {
  id: string
  type: WorkerType
  model: string
  
  // Lifecycle
  spawn(workdir: string): Promise<void>
  terminate(): Promise<void>
  
  // Execution
  execute(prompt: string, context: BeadContext): Promise<ExecutionResult>
  
  // Observability
  onProgress(callback: (signal: ProgressSignal) => void): void
  onOutput(callback: (line: string) => void): void
  getState(): WorkerState
}
```

#### Option B: Pragmatic Shell + Parse

```typescript
interface WorkerConfig {
  type: string
  model: string
  
  // Just the command template
  command: string[]  // e.g. ['claude', '--headless', '-p', '{{prompt}}']
  workdirFlag: string
  
  // Output parsing
  progressPatterns: {
    fileChanged: RegExp
    error: RegExp
    complete: RegExp
  }
  
  useGitProgress: boolean  // Universal fallback
}
```

**Recommendation**: Start with Option B for speed, add proper adapters for workers that need special handling (Claude Code's rich JSON output).

---

## Scheduling & Learning

The scheduler learns which (task_type, orchestrator, model) tuples work best using a contextual bandit approach.

```typescript
interface TaskSignature {
  projectId: string
  languages: string[]
  taskCategory: 'bug' | 'feature' | 'refactor' | 'test' | 'docs'
  estimatedScope: 'small' | 'medium' | 'large'
  hasTests: boolean
  promptEmbedding: number[]  // For similarity matching
}

interface PerformanceMemory {
  record(
    taskSignature: TaskSignature,
    worker: WorkerConfig,
    outcome: {
      success: boolean
      duration: number
      tokensUsed: number
      humanInterventions: number
      unstuckInvocations: number
    }
  ): void
  
  // Thompson sampling or UCB for selection
  suggestWorker(
    taskSignature: TaskSignature,
    availableWorkers: WorkerConfig[]
  ): WorkerConfig
}
```

Start with ε-greedy (90% best known, 10% exploration), graduate to Thompson sampling with sufficient data.

---

## Progress Monitoring & Unstuck Handling

### Progress Signals

```typescript
interface ProgressSignals {
  // Git-based
  filesChanged: number
  linesAdded: number
  linesRemoved: number
  commitsCreated: number
  
  // Output-based
  testsPassingDelta: number
  errorsResolved: number
  
  // Time-based
  timeSinceLastProgress: number
  totalElapsed: number
  
  // Agent-reported
  selfReportedProgress: number
  lastAction: string
}

function isStuck(signals: ProgressSignals): boolean {
  // No git activity in 5 minutes while actively running
  if (signals.timeSinceLastProgress > 300 && signals.filesChanged === 0) {
    return true
  }
  // Spinning: lots of activity but tests still failing
  if (signals.commitsCreated > 5 && signals.testsPassingDelta <= 0) {
    return true
  }
  return false
}
```

### Unstuck Handler

When stuck, reassign to a different worker class with enhanced context:

```typescript
class UnstuckHandler {
  async handleStuck(bead: Bead, failedWorker: WorkerClass): Promise<UnstuckAction> {
    const attemptedWorkers = bead.attempts.map(a => a.worker)
    const availableWorkers = workerPool.filter(w => 
      !attemptedWorkers.some(aw => 
        aw.orchestrator === w.orchestrator && aw.model === w.model
      )
    )
    
    if (availableWorkers.length === 0) {
      return { action: 'escalate', reason: 'All workers exhausted' }
    }
    
    // Prefer different orchestrator first, then different model
    const nextWorker = this.selectNextWorker(failedWorker, availableWorkers)
    
    // Enhance prompt with failure context
    const enhancedPrompt = await this.enhancePromptWithContext(
      bead.prompt,
      { priorAttempts: bead.attempts, failureAnalysis: ... }
    )
    
    return { action: 'reassign', worker: nextWorker, prompt: enhancedPrompt }
  }
}
```

---

## Project Inference

Ringmaster infers project context from code artifacts, then refines with RLM.

```typescript
interface ProjectContext {
  languages: LanguageInfo[]
  frameworks: string[]
  packageManager: string
  testRunner: string
  testCommand: string
  
  recentCommits: CommitSummary[]
  activeAuthors: string[]
  hotFiles: string[]
  
  entryPoints: string[]
  configFiles: string[]
  
  conventions: {
    codeStyle: string
    branchStrategy: string
    commitStyle: string
    customRules: string[]
  }
}

class ProjectInferrer {
  async infer(repoPath: string): Promise<ProjectContext> {
    // Static analysis: package.json, pyproject.toml, git log, structure
    const context = await this.staticInference(repoPath)
    
    // RLM refinement for conventions, patterns, domain knowledge
    return this.refineWithRLM(context, sampleFiles)
  }
}
```

---

## Hot-Reload System

### Three Levels

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         RINGMASTER                                       │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    STABLE CORE (rarely changes)                  │   │
│  │  • Process supervisor                                            │   │
│  │  • SQLite connection pool                                        │   │
│  │  • WebSocket hub                                                 │   │
│  │  • Work queue (in-flight protection)                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              │ loads/reloads                             │
│                              ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                  HOT-SWAPPABLE COMPONENTS                        │   │
│  │                                                                  │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │   │
│  │  │   Workers    │ │   Prompts    │ │  Scheduler   │             │   │
│  │  │   (configs)  │ │   (RLM)      │ │  (algorithm) │             │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘             │   │
│  │                                                                  │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │   │
│  │  │  Inference   │ │   Unstuck    │ │  Summarizer  │             │   │
│  │  │  (project)   │ │   (logic)    │ │  (templates) │             │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Level 1: Config/Prompt Reload

```
ringmaster/
├── config/
│   ├── workers.yaml
│   ├── prompts/
│   │   ├── refiner.md
│   │   ├── unstuck.md
│   │   ├── summarizer.md
│   │   └── inference.md
│   └── scheduler.yaml
```

Watch files, reload on change. Components always pull latest config.

#### Level 2: Logic Module Reload

Dynamic imports with cache busting for TypeScript modules.

#### Level 3: Process Isolation

Separate processes for each component, supervisor handles upgrades with draining.

---

## Validation & Rollback Pipeline

### Upgrade Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         UPGRADE PIPELINE                                 │
│                                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ PROPOSE  │───▶│ VALIDATE │───▶│  SHADOW  │───▶│  CANARY  │──┐       │
│  │          │    │ (static) │    │(parallel)│    │(gradual) │  │       │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │       │
│                        │              │               │         │       │
│                        ▼              ▼               ▼         │       │
│                   ┌─────────────────────────────────────┐      │       │
│                   │           METRICS STORE             │      │       │
│                   └─────────────────────────────────────┘      │       │
│                                                                 │       │
│       ┌─────────────────────────────────────────────────────────┘       │
│       ▼                                                                  │
│  ┌──────────┐    ┌──────────┐                                           │
│  │ PROMOTE  │───▶│ COMPLETE │                                           │
│  └──────────┘    └──────────┘                                           │
│       │                                                                  │
│       │ (if metrics regress)                                            │
│       ▼                                                                  │
│  ┌──────────┐                                                           │
│  │ ROLLBACK │                                                           │
│  └──────────┘                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Stage Details

1. **Static Validation**: Schema compatibility, syntax/parse check, placeholder verification, type checking, invariant tests
2. **Shadow Testing**: Replay test corpus, compare outputs (exact for deterministic, semantic similarity + LLM-as-judge for stochastic)
3. **Live Shadow**: Run both versions on live traffic, only use current's output, collect metrics
4. **Canary**: Gradual traffic shift (5% → 25% → 50% → 100%) with automatic rollback thresholds

### Canary Configuration

```typescript
interface CanaryConfig {
  stages: [
    { percentage: 5, minDuration: 60000, requiredMetrics: {...} },
    { percentage: 25, minDuration: 300000, requiredMetrics: {...} },
    { percentage: 50, minDuration: 600000, requiredMetrics: {...} },
    { percentage: 100, minDuration: 600000, requiredMetrics: {...} }
  ],
  rollbackThresholds: {
    errorRateThreshold: 0.1,
    latencyDegradation: 1.5,
    successRateDrop: 0.9
  }
}
```

---

## Web UX

### Design Principles

1. **Attention Budget**: Decisions requiring human input float to top
2. **Progressive Disclosure**: Dashboard → Project → Bead → Worker logs
3. **Keyboard-First**: vim-style navigation, command palette (⌘K)
4. **Real-Time Without Chaos**: WebSocket updates, smooth animations

### Navigation

```
[1] Dashboard        Overview, metrics, health
[2] Projects         Configure repos, inference
[3] Queue            Beads kanban, backlog
[4] Decisions  (3)   Human-in-loop inbox
[5] Workers          Pool status, assignments
[6] Activity         Live feed, search logs
[7] Upgrades         Self-improvement pipeline
```

### Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Dashboard                                                               │
│                                                                          │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐            │
│  │  DECISIONS      │ │  IN PROGRESS    │ │  COMPLETED      │            │
│  │     3 ⚠️        │ │     12          │ │     47 today    │            │
│  │  2 blocking     │ │  8 healthy      │ │  94% success    │            │
│  │  1 review       │ │  3 slow         │ │                 │            │
│  │                 │ │  1 stuck        │ │                 │            │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘            │
│                                                                          │
│  WORKER POOL                                                15/20 busy  │
│  ───────────────────────────────────────────────────────────────────    │
│  Claude Code    ████████████░░░░  8/12   Sonnet(5) Opus(2) GLM(1)       │
│  OpenCode       ████░░░░░░░░░░░░  3/8    Gemini(2) GPT-4o(1)            │
│  Kilo           ██░░░░░░░░░░░░░░  2/6    Sonnet(2)                      │
│  Goose          ██░░░░░░░░░░░░░░  2/4    Local(2)                       │
│                                                                          │
│  RECENT ACTIVITY                                                         │
│  ───────────────────────────────────────────────────────────────────    │
│  2m ago   ✓ bead-4f2a  "Add user avatar upload"     CC/Sonnet           │
│  3m ago   → bead-8b1c  "Fix payment retry logic"    OC/Gemini           │
│  5m ago   ⚠ bead-2d9e  STUCK - reassigning          CC/Opus→Kilo        │
│  7m ago   ? bead-1a3f  DECISION NEEDED              blocked             │
└─────────────────────────────────────────────────────────────────────────┘
```

### Queue (Kanban)

```
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ BACKLOG (8) │ │ QUEUED (14) │ │ WORKING (12)│ │ REVIEW (3)  │
├─────────────┤ ├─────────────┤ ├─────────────┤ ├─────────────┤
│ ┌─────────┐ │ │ ┌─────────┐ │ │ ┌─────────┐ │ │ ┌─────────┐ │
│ │ #52     │ │ │ │ #41     │ │ │ │ #38     │ │ │ │ #29     │ │
│ │ rho     │ │ │ │ rho     │ │ │ │ trading │ │ │ │ rho     │ │
│ │ Add SSO │ │ │ │ Fix     │ │ │ │ Impl    │ │ │ │ Review: │ │
│ │ ○○○○○   │ │ │ │ webhook │ │ │ │ backtest│ │ │ │ Changed │ │
│ └─────────┘ │ │ └─────────┘ │ │ │ CC/Son  │ │ │ │ approach│ │
│             │ │             │ │ └─────────┘ │ │ └─────────┘ │
│ ...6 more   │ │ ...12 more  │ │ ...10 more  │ │             │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

### Decisions Inbox

Optimized for fast triage with two categories:

- **Blocking**: Agent can't proceed without input
- **Review**: Work complete, needs approval

Quick actions for simple decisions, full response box for complex ones.

---

## File Viewer

### Supported Types

```
TEXT/CODE           DOCUMENTS           MEDIA            DATA
──────────────      ──────────────      ──────────────   ──────────
• .md  (render)     • .pdf (embed)      • .png/.jpg      • .json
• .py  (highlight)  • .docx (convert)   • .svg           • .csv
• .ts  (highlight)  • .html (iframe)    • .mp3 (audio)   • .yaml
• .sql (highlight)  • .tex (render)     • .mp4 (video)   • .parquet

Special:
• .research.md  - Research notebook format with sections
• .summary.md   - Agent-generated summaries
• .diff         - Git diffs with syntax highlighting
```

### Research Notebook Format

```markdown
# Research Document

## Metadata
- Bead: #34
- Agent: CC/Opus
- Status: In progress (Section 4/6)

## Table of Contents
✓ 1. Executive Summary
✓ 2. Market Size & Growth
→ 3. Technology Trends (in progress)
○ 4. Recommendations

## § 1. Executive Summary
[Content with source citations]

┌─ Source ──────────────────────────────┐
│ CB Insights Q4 2024 Fintech Report    │
│ Confidence: High                      │
└───────────────────────────────────────┘
```

### Features

- **Versioning**: Every file change tracked, diff viewing
- **Annotations**: Comment on specific parts, conversations with agents
- **Relationships**: See how files link to each other
- **Multi-format rendering**: Code, data, documents, media
- **Export**: Markdown, PDF, Word, Notion, Google Docs

---

## Tech Stack

### Frontend

```
Framework:    SvelteKit or Next.js (App Router)
Styling:      Tailwind + shadcn/ui
State:        Zustand or Jotai
Real-time:    Native WebSocket
Data:         TanStack Query + WebSocket
DnD:          dnd-kit (kanban)
Terminal:     xterm.js (live logs)
Charts:       Recharts or Chart.js
```

### Backend

```
API:          Hono (TypeScript) or FastAPI (Python)
WebSocket:    ws (Node) or native Hono WS
Database:     SQLite + better-sqlite3 + Drizzle ORM
Queue:        SQLite-based initially, BullMQ + Redis if needed
```

### SQLite Scaling

| Scenario | SQLite Handles It? |
|----------|-------------------|
| 50 agents, single machine | ✅ Easily |
| 200 agents, single machine | ⚠️ Write contention starts |
| Distributed workers | ❌ Need Postgres/Turso |

---

## Related Projects & Prior Art

### Existing Orchestrators

- **claude-flow** (ruvnet): Queue-based, RAG integration, MCP protocol
- **claude_code_agent_farm** (Dicklesworthstone): 20-50 parallel agents, Redis queue
- **Maestro** (Doriandarko): Opus orchestrator → Haiku workers, task decomposition
- **oh-my-claudecode** (Yeachan-Heo): 5 execution modes, parallel workers

### Gap Ringmaster Fills

No existing tool provides:
```
Multimodal Input → Refinement LLM → Context Enrichment (RAG/memory) → Priority Queue → Heterogeneous Agent Pool → Learning Scheduler
```

Most assume text-in and skip the refinement layer entirely.

---

## License

TBD

---

*Document generated from design conversation, January 28, 2026*
