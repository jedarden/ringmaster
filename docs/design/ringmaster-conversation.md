# Ringmaster Design Conversation - Raw Transcript

> Conversation date: January 28, 2026

---

## Initial Question

**User**: What GitHub users or other LLM coding experts have a natural language orchestrator?

The expectation from me is some sort of interface which describes a project, it's context, and maybe chat history into which I can put multimedia (text/audio/images)

The orchestrator refines the user input, enriches with supplemental context (maybe with RLM?) then queues the prompt and work for an agent to pick up as they become free.

Expectation is there are N agents and > N backlog of work for the agents to process.

---

## Claude Response: Existing Tools Survey

### Closest Matches

1. **claude-flow** (ruvnet) - Most aligned with queue-based, N-agents architecture
2. **claude_code_agent_farm** (Dicklesworthstone) - Exactly the N-agents > backlog pattern
3. **Maestro** (Doriandarko) - Classic orchestrator → sub-agent architecture
4. **oh-my-claudecode** (Yeachan-Heo) - 5 execution modes including parallel workers

### The Gap

Nobody has built a clean:
```
Multimodal Input → Refinement LLM → Context Enrichment (RAG/memory) → Priority Queue → Agent Pool
```

---

## User: Ringmaster Concept

**User**: I've been noodling on an idea.

Codenamed ringmaster. Sort of like how all the LLM orchestrators are chaotic like different acts of a circus.

Expectation is a UX where the user defines projects.

Prompts gets enhanced with RLM + supplemental context if needed before being turned into a kanban card or something similar to a steve yegge style bead.

A pool of different LLM workers (Claude code headless CLI, open code CLI, kilo code CLI, codebuff, goose, etc) run through Ralph wiggum style loops until the bead is processed.

Expectation is there will be more units of work than available workers so.

At some point the UX will need to prompt the user to answer a question or make a decision. So should be able to summarize what was done.

---

## Claude Response: Architecture v1

[Detailed architecture diagram and bead schema provided]

Key questions raised:
1. Bead Schema - What's the unit of work?
2. Worker Abstraction - They all speak different dialects
3. The RLM Refinement Step - This is the secret sauce
4. Human-in-the-Loop Surfacing - When to interrupt vs. let circus keep running

---

## User: Design Refinements

**User**: Interface should ideally be web based.

Scheduling should probably be initially random with some memory component to identify which combination of coding orchestrator and model are suited for what tasks.

Failure modes should probably be measured in some sort of progress. Maybe if stuck invoke another agent with some sort of supplemental context to try and get unstuck or hand-off the task.

Expectation is the RLM process takes all the output notes and relevant git commits to summarize to the user.

State can be sqlite for now. Unclear how well it scales with potentially dozens or hundreds of agents working at the same time.

---

## Claude Response: Architecture v2

- Learning Scheduler using contextual bandit (ε-greedy → Thompson sampling)
- Progress Monitor based on git activity and output patterns
- Unstuck Handler that reassigns to different worker class
- SQLite scaling analysis (fine to 50 agents, contention at 200, distributed needs Postgres)

---

## User: Worker Adapter Question

**User**: 
1) not sure. How would either option work? [clean abstractions vs pragmatic shell]
2) ringmaster should infer from existing code artifacts and context. This will likely require tuning by the RLM orchestrator.
3) Same pool but different type/class. E.g. Claude code sonnet failed. Maybe Claude code glm 4.7 can solve it.

---

## Claude Response: Worker Adapter Deep Dive

### Option A: Clean Abstractions
- Type-safe interface all workers implement
- Pros: Testable, mockable, easy to add workers
- Cons: Upfront investment, maintenance burden

### Option B: Pragmatic Shell + Parse
- Config-driven, shell out and parse output
- Git-based progress as universal fallback
- Pros: Add workers via config, faster to prototype
- Cons: Fragile parsing, less type safety

**Recommendation**: Hybrid - start with Option B, add proper adapters for workers that need special handling.

### Project Inference
- Static analysis (package.json, pyproject.toml, git log)
- RLM refinement for conventions, patterns, domain knowledge

### Unstuck Handler
- Same pool, different worker class
- Prefer different orchestrator first, then different model
- Enhanced prompt includes failure context from prior attempts

---

## User: Hot-Reload Question

**User**: How can the different components of ringmaster be made to hot-reload?

That should in theory make it easier for the different components of ringmaster to upgrade itself.

---

## Claude Response: Hot-Reload System

### Three Levels

1. **Level 1: Config/Prompt Reload** - File watching, immediate effect
2. **Level 2: Logic Module Reload** - Dynamic imports with cache busting
3. **Level 3: Process Isolation** - Separate processes, supervisor handles upgrades

### Self-Upgrade Flow
- Components can propose upgrades to themselves
- RLM generates the change
- Validation → Shadow testing → Apply/Rollback

---

## User: Validation System Question

**User**: Figure out the validation/rollback system for self upgrades. There's probably some sort of shadow/parallel testing that will need to be established to confirm replacement components retain backwards compatibility.

---

## Claude Response: Validation & Rollback Pipeline

### Four Stages

1. **Static Validation**: Schema compatibility, syntax, type checking, invariants
2. **Shadow Testing**: Replay test corpus, compare outputs
3. **Live Shadow**: Both versions on live traffic, only use current's output
4. **Canary Deployment**: 5% → 25% → 50% → 100% with auto-rollback

### Key Concepts
- Component versioning with full lineage
- Interface contracts (schema, invariants, performance bounds)
- Test case capture from production (1% sampling)
- LLM-as-judge for semantic comparison of stochastic outputs

---

## User: Web UX Request

**User**: Focus on the web ux

---

## Claude Response: Web UX Design

### Principles
1. Attention Budget - Decisions float to top
2. Progressive Disclosure - Dashboard → Project → Bead → Logs
3. Keyboard-First - vim-style, command palette
4. Real-Time Without Chaos - WebSocket, smooth animations

### Screens Detailed
1. Dashboard - Glance and go view
2. Queue - Kanban with backlog, queued, working, review columns
3. Bead Detail - Slide-over panel with full context
4. Decisions Inbox - Blocking vs Review categories
5. Activity Stream - Real-time feed with filtering
6. Worker Detail - Live output, git diff
7. Upgrades Pipeline - Canary progress, pending reviews

---

## User: File Viewer Request

**User**: There will probably need to be some sort of file viewer especially for research type tasks.

---

## Claude Response: File Viewer Design

### Supported Types
- Text/Code (syntax highlighting)
- Documents (PDF, Word, HTML)
- Media (images, audio, video)
- Data (JSON, CSV, Parquet)

### Special Formats
- `.research.md` - Research notebook with sections, sources, progress
- Version tracking with diff view
- Annotation system for comments/conversations
- Export to multiple formats

### Data Model
- `ProjectFile` with versions, relationships, citations
- `FileComment` with anchors for position
- `ResearchNotebook` extension for research tasks

---

## User: Export Request

**User**: How can this full conversation be exported and added to a GitHub repo

---

*End of conversation transcript*
