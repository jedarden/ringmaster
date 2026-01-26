# Open Architecture Decisions

## Overview

This document captures architectural decisions for Ringmaster based on research and constraints. Each section addresses a previously open question.

## 1. Git Concurrency

**Decision: Git worktrees, one per worker.**

### Research Findings

[Git worktrees have emerged as the standard](https://medium.com/@dennis.somerville/parallel-workflows-git-worktrees-and-the-art-of-managing-multiple-ai-agents-6fa3dc5eec1d) for multi-agent coding:

- [Worktrees share a single `.git` directory](https://medium.com/@mabd.dev/git-worktrees-the-secret-weapon-for-running-multiple-ai-coding-agents-in-parallel-e9046451eb96), making them lightweight
- Each agent gets an isolated working directory
- No branch switching, no context destruction
- Tools like [`par`](https://github.com/coplane/par) and Claude Squad use this pattern
- [Cursor 2.0 uses worktrees](https://nx.dev/blog/git-worktrees-ai-agents) for up to 8 concurrent agents

### Implementation

```
/workspace/
├── project-main/              # Main checkout (user's view)
├── project.worktrees/
│   ├── worker-claude-1/       # Worktree for claude-code-1
│   ├── worker-claude-2/       # Worktree for claude-code-2
│   ├── worker-codex-1/        # Worktree for codex-1
│   └── ...
```

Each worker:
1. Gets assigned a worktree on startup
2. Creates a branch for their task: `ringmaster/<task-id>`
3. Commits atomically when done
4. Worktree is cleaned/recycled for next task

Merge strategy:
- Workers commit to their branch
- Ringmaster merges to main after validation
- Conflicts trigger decision request to user

## 2. Task Decomposition / Bead Mapping

**Decision: User input maps to existing beads OR creates new beads. The enrichment layer determines this.**

### The Flow

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BEAD MAPPER                                                         │
│                                                                      │
│  1. Parse user intent                                                │
│  2. Search existing beads for semantic match                         │
│  3. If match found:                                                  │
│     └─ Update existing bead with new context/instructions           │
│  4. If no match:                                                     │
│     └─ Create new bead(s)                                           │
│  5. Set/update dependencies                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Matching Logic

```python
def map_input_to_beads(user_input: str, project: Project) -> list[Bead]:
    """Map user input to existing or new beads."""

    # 1. Extract intent
    intent = extract_intent(user_input)

    # 2. Search existing beads
    existing = search_beads(
        project_id=project.id,
        query=intent.summary,
        status=["draft", "ready", "in_progress", "blocked"]
    )

    # 3. Score matches
    matches = []
    for bead in existing:
        score = semantic_similarity(intent.summary, bead.title + bead.description)
        if score > 0.7:  # High confidence match
            matches.append((bead, score))

    if matches:
        # Update existing bead(s)
        matches.sort(key=lambda x: x[1], reverse=True)
        primary_bead = matches[0][0]
        primary_bead.add_context(user_input)
        return [primary_bead]

    else:
        # Create new bead(s)
        # Let the worker decompose during execution
        new_bead = create_bead(
            title=intent.summary,
            description=user_input,
            type="task"
        )
        return [new_bead]
```

### Key Insight

Per [Steve Yegge's Beads philosophy](https://steve-yegge.medium.com/introducing-beads-a-coding-agent-memory-system-637d7d92514a):
- Beads track execution, not planning
- Let agents decompose during work
- File beads for work > 2 minutes
- Agents create sub-beads as needed during Ralph loops

## 3. Success/Failure Validation

**Decision: Separate validation worker reviews completed work. Tests are primary signal.**

### Research Findings

From [Anthropic's eval guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents):
- Deterministic graders (tests) are natural for coding agents
- "Does the code run and do the tests pass?" is the core question
- [SWE-bench](https://arxiv.org/abs/2310.06770) grades by running test suites
- LLM-as-judge requires calibration with human experts

### Implementation

```
Worker completes task
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  VALIDATION PIPELINE                                                 │
│                                                                      │
│  1. Run test suite (primary signal)                                  │
│     ├─ All pass → Proceed to step 2                                 │
│     └─ Any fail → Return to worker with failures                    │
│                                                                      │
│  2. Static analysis (linting, type checking)                         │
│     ├─ Pass → Proceed to step 3                                     │
│     └─ Fail → Return to worker                                      │
│                                                                      │
│  3. Assign validation worker (different from implementation worker) │
│     ├─ Reviews code for correctness, style, security                │
│     ├─ Checks acceptance criteria                                   │
│     └─ Approves OR returns with feedback                            │
│                                                                      │
│  4. Deploy to staging (if applicable)                                │
│     └─ Smoke tests against running service                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Validation Worker Prompt

```markdown
You are validating work completed by another agent.

Task: {task.title}
Acceptance Criteria: {task.acceptance_criteria}

Changes made:
{git_diff}

Test results:
{test_output}

Review for:
1. Does the implementation satisfy the acceptance criteria?
2. Are there any obvious bugs or edge cases missed?
3. Does the code follow project conventions?
4. Are there security concerns?

Output:
- APPROVED: Ready for merge
- NEEDS_WORK: [specific feedback]
```

## 4. Worker Health & Recovery

**Decision: Track commits for undo. Monitor logs for activity vs hang detection.**

### Commit-Based Recovery

Each worker's progress is tracked via commits:

```python
class WorkerSession:
    worker_id: str
    task_id: str
    worktree_path: str
    branch_name: str
    commits: list[str]  # SHA list for rollback

    def checkpoint(self, message: str):
        """Create checkpoint commit."""
        sha = git_commit(self.worktree_path, message)
        self.commits.append(sha)
        db.update_session(self)

    def rollback(self, to_commit: str = None):
        """Rollback to previous checkpoint."""
        target = to_commit or self.commits[-2]  # Previous commit
        git_reset_hard(self.worktree_path, target)
        self.commits = self.commits[:self.commits.index(target) + 1]
```

### Hang Detection

Monitor worker output to distinguish extended thinking from hangs:

```python
class WorkerMonitor:
    def __init__(self, worker_id: str, log_path: str):
        self.worker_id = worker_id
        self.log_path = log_path
        self.last_activity = now()
        self.last_size = 0

    def check_health(self) -> WorkerStatus:
        current_size = os.path.getsize(self.log_path)

        if current_size > self.last_size:
            # Log is growing - worker is active
            self.last_activity = now()
            self.last_size = current_size
            return WorkerStatus.ACTIVE

        idle_seconds = (now() - self.last_activity).seconds

        if idle_seconds < 60:
            return WorkerStatus.THINKING  # Normal pause
        elif idle_seconds < 300:
            return WorkerStatus.SLOW  # Extended thinking
        else:
            return WorkerStatus.HUNG  # Likely stuck

    def get_recent_output(self, lines: int = 50) -> str:
        """Get recent log output for debugging."""
        return tail(self.log_path, lines)
```

### Recovery Actions

| Status | Action |
|--------|--------|
| ACTIVE | None |
| THINKING | None, log for metrics |
| SLOW | Alert, consider timeout extension |
| HUNG | Kill worker, rollback to last commit, reassign task |

## 5. Cost Management

**Decision: No budgets for now. Unlimited plans in use.**

Track for observability but don't enforce limits:

```python
@dataclass
class CostEvent:
    worker_id: str
    task_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime

def log_cost(event: CostEvent):
    db.insert("cost_events", event)
    # No enforcement, just tracking
```

Future consideration: Per-project cost dashboards for visibility.

## 6. Security & Sandboxing

**Decision: Containerized execution. K8s for deployment testing. Sealed secrets.**

### Container Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  WORKSPACE HOST                                                      │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  WORKER CONTAINER                                               ││
│  │                                                                 ││
│  │  • Worker CLI (Claude Code, Codex, etc.)                       ││
│  │  • Project worktree mounted                                    ││
│  │  • Build tools (cargo, npm, etc.)                              ││
│  │  • Test runners                                                ││
│  │  • No secrets (env vars stripped)                              ││
│  │                                                                 ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  Workers can:                                                        │
│  ✓ Read/write files in worktree                                     │
│  ✓ Run builds and tests                                             │
│  ✓ Make network requests (for research)                             │
│  ✗ Access secrets                                                   │
│  ✗ Access other worktrees                                           │
│  ✗ Access host system                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Secrets & Deployment Testing

```
Secrets are sealed into K8s cluster
        │
        ▼
To test with secrets:
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. Worker creates deployment manifests                             │
│  2. Ringmaster triggers K8s deployment to staging namespace         │
│  3. Sealed secrets are decrypted by cluster                         │
│  4. Worker runs integration tests against staging                   │
│  5. Staging namespace torn down after tests                         │
└─────────────────────────────────────────────────────────────────────┘
```

## 7. Decision Logs (Minimizing User Input)

**Decision: Workers maintain decision logs. Test alternatives before asking user.**

### Decision Log Pattern

```python
@dataclass
class DecisionEntry:
    id: str
    question: str
    options: list[str]
    tested: dict[str, TestResult]  # option -> result
    chosen: str | None
    rationale: str | None
    requires_user: bool

class DecisionLog:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.entries = []

    def log_uncertainty(self, question: str, options: list[str]) -> DecisionEntry:
        entry = DecisionEntry(
            id=generate_id(),
            question=question,
            options=options,
            tested={},
            chosen=None,
            rationale=None,
            requires_user=False
        )
        self.entries.append(entry)
        return entry

    def record_test(self, entry_id: str, option: str, result: TestResult):
        entry = self.get_entry(entry_id)
        entry.tested[option] = result

        # If one option clearly works and others don't, auto-decide
        if self.can_auto_decide(entry):
            entry.chosen = self.get_best_option(entry)
            entry.rationale = "Auto-selected based on test results"
        elif self.all_options_tested(entry):
            entry.requires_user = True  # Need human input
```

### Worker Prompt Addition

```markdown
## Decision Handling

When uncertain between multiple approaches:
1. Log the decision point to your decision log
2. Implement and test each viable option
3. If one option clearly works (tests pass, others fail):
   - Choose it automatically
   - Document rationale
4. If multiple options work or all fail:
   - Request user decision
   - Provide test results for each option

Goal: Minimize user interruptions through empirical testing.
```

## 8. Multi-User

**Decision: Single user for now. Separate Ringmaster instances for other users.**

Future multi-user would involve:
- Shared git repos (already supported by git)
- Separate Ringmaster instances per user
- No shared worker pools
- Coordination via git (branches, PRs)

## 9. Research Storage

**Decision: Use model's built-in web search. Store research in project's research folder.**

### Research Flow

```
Research needed
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. Worker uses built-in web search (if available)                  │
│     └─ Claude: Native web search                                    │
│     └─ Others: MCP web search tool                                  │
│                                                                      │
│  2. Results stored in project                                        │
│     └─ /project/research/                                           │
│         ├─ 2026-01-26-jwt-best-practices.md                         │
│         ├─ 2026-01-26-rust-axum-auth.md                             │
│         └─ ...                                                       │
│                                                                      │
│  3. Research indexed for context enrichment                          │
│     └─ Available as "Research" source for future tasks              │
└─────────────────────────────────────────────────────────────────────┘
```

## 10. Worker Type Flexibility

**Decision: Ralph loops are default but not required. Workers are configurable.**

### Worker Configurations

```toml
[[workers]]
name = "claude-code-1"
type = "claude-code"
mode = "ralph"  # Iterative loop until done
max_iterations = 10

[[workers]]
name = "claude-research"
type = "claude-code"
mode = "single"  # One-shot, no loop
purpose = "research"

[[workers]]
name = "codex-1"
type = "codex"
mode = "ralph"
max_iterations = 5

[[workers]]
name = "review-bot"
type = "claude-code"
mode = "single"
purpose = "validation"
```

### Mode Behaviors

| Mode | Behavior |
|------|----------|
| `ralph` | Iterate: implement → test → fix → repeat until done or max |
| `single` | One-shot execution, return result |
| `streaming` | Long-running, continuous output (future) |

## 11. Model Selection / Routing

**Decision: Research-based routing. Complexity determines model.**

### Research Findings

From [LLMRouter](https://www.marktechpost.com/2025/12/30/meet-llmrouter-an-intelligent-routing-system-designed-to-optimize-llm-inference-by-dynamically-selecting-the-most-suitable-model-for-each-query/) and [RouteLLM](https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf):
- Dynamic routing can reduce costs 2x+ without quality loss
- Task complexity is the primary routing signal
- [Hybrid routing saves 39% on AI costs](https://www.requesty.ai/blog/intelligent-llm-routing-in-enterprise-ai-uptime-cost-efficiency-and-model)

### Implementation

```python
def select_model_for_task(task: Task) -> str:
    """Route task to appropriate model based on complexity."""

    complexity = estimate_complexity(task)

    if complexity == "simple":
        # Refactoring, simple fixes, formatting
        return "claude-haiku" or "gpt-4o-mini"

    elif complexity == "moderate":
        # Feature implementation, bug fixes
        return "claude-sonnet" or "gpt-4o"

    elif complexity == "complex":
        # Architecture, multi-file changes, security
        return "claude-opus" or "o1"

    elif task.type == "research":
        # Research tasks - speed matters
        return "claude-sonnet"  # Good balance

    elif task.type == "validation":
        # Code review - thorough but not creative
        return "claude-sonnet"

def estimate_complexity(task: Task) -> str:
    """
    Estimate task complexity using DETERMINISTIC heuristics.
    No LLM calls - pure rule-based scoring.
    """

    score = 0

    # === File count signals ===
    file_count = len(task.suggested_files)
    if file_count == 0:
        score += 0  # Unknown, assume moderate
    elif file_count == 1:
        score += 0  # Single file = simple
    elif file_count <= 3:
        score += 1  # Few files = moderate
    else:
        score += 2  # Many files = complex

    # === Keyword signals (deterministic pattern matching) ===
    title_lower = task.title.lower()
    desc_lower = task.description.lower()
    text = title_lower + " " + desc_lower

    # Simple indicators
    simple_keywords = ["typo", "rename", "format", "lint", "comment", "todo", "fixme"]
    if any(kw in text for kw in simple_keywords):
        score -= 1

    # Complex indicators
    complex_keywords = ["architect", "refactor", "migrate", "security", "auth",
                        "database", "schema", "api design", "breaking change"]
    complex_matches = sum(1 for kw in complex_keywords if kw in text)
    score += complex_matches

    # === Dependency signals ===
    if len(task.dependencies) > 2:
        score += 1  # Many dependencies = integration work

    # === Bead type signals ===
    if task.type == "epic":
        score += 2  # Epics are inherently complex
    elif task.type == "subtask":
        score -= 1  # Subtasks are granular

    # === Priority signals ===
    if task.priority == "P0":
        score += 1  # Critical often means complex

    # === Threshold mapping ===
    if score <= 0:
        return "simple"
    elif score <= 2:
        return "moderate"
    else:
        return "complex"
```

### Reflexion-Based Learning

Static heuristics are the **cold start**. Over time, Ringmaster learns from experience using [Reflexion](https://arxiv.org/abs/2303.11366) patterns.

#### Reasoning Bank Schema

```sql
CREATE TABLE task_outcomes (
    id INTEGER PRIMARY KEY,
    task_id TEXT NOT NULL,

    -- Task signals (for similarity matching)
    file_count INTEGER,
    keywords TEXT,           -- JSON array
    bead_type TEXT,
    has_dependencies BOOLEAN,
    description_embedding BLOB,  -- For semantic similarity

    -- Execution
    model_used TEXT NOT NULL,
    iterations INTEGER,
    duration_seconds INTEGER,

    -- Outcome
    success BOOLEAN NOT NULL,
    failure_reason TEXT,

    -- Reflection (generated post-task)
    reflection TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_outcomes_model ON task_outcomes(model_used, success);
CREATE INDEX idx_outcomes_type ON task_outcomes(bead_type, success);
```

#### Learning Loop

```python
def select_model_with_learning(task: Task, reasoning_bank: ReasoningBank) -> str:
    """Route task using learned experience + static heuristics."""

    # Find similar past tasks
    similar = reasoning_bank.find_similar(
        keywords=extract_keywords(task),
        bead_type=task.type,
        file_count=len(task.suggested_files),
        min_similarity=0.7
    )

    if len(similar) < MIN_SAMPLES_FOR_LEARNING:
        # Not enough data - use static heuristics only
        return select_model_static(task)

    # Compute success rates per model
    model_scores = {}
    for model in AVAILABLE_MODELS:
        outcomes = [t for t in similar if t.model_used == model]
        if len(outcomes) >= 3:  # Need minimum samples
            success_rate = sum(1 for t in outcomes if t.success) / len(outcomes)
            model_scores[model] = success_rate

    if not model_scores:
        return select_model_static(task)

    # Blend static and learned
    static_choice = select_model_static(task)
    learned_choice = max(model_scores, key=model_scores.get)

    # If learned significantly outperforms static, use learned
    if model_scores.get(learned_choice, 0) > model_scores.get(static_choice, 0) + 0.1:
        return learned_choice

    return static_choice

# Configuration
MIN_SAMPLES_FOR_LEARNING = 10
```

#### Reflection Generation

After task completion, generate a reflection for the reasoning bank:

```python
def record_outcome(task: Task, result: TaskResult, validation: ValidationResult):
    """Record task outcome with reflection for future learning."""

    outcome = TaskOutcome(
        task_id=task.id,
        file_count=len(task.suggested_files),
        keywords=extract_keywords(task),
        bead_type=task.type,
        has_dependencies=len(task.dependencies) > 0,
        model_used=result.model,
        iterations=result.iterations,
        duration_seconds=result.duration,
        success=validation.approved,
        failure_reason=validation.rejection_reason if not validation.approved else None,
    )

    # Generate reflection (use cheap model)
    if validation.approved:
        outcome.reflection = f"Succeeded on {task.type} task. " \
                            f"Model handled {outcome.file_count} files in {outcome.iterations} iterations."
    else:
        # Extract learning from failure
        outcome.reflection = generate_failure_reflection(task, result, validation)

    reasoning_bank.insert(outcome)

def generate_failure_reflection(task: Task, result: TaskResult, validation: ValidationResult) -> str:
    """Generate actionable reflection from failure."""

    prompt = f"""
    Task: {task.title}
    Model: {result.model}
    Outcome: Failed
    Reason: {validation.rejection_reason}

    In one sentence, what should be learned for future model selection?
    Focus on: Was this task too complex for the model? What signals indicated that?
    """

    # Use cheap model for reflection generation
    return llm_generate(prompt, model="claude-haiku")
```

#### Multi-Agent Reflection

To avoid single-agent blind spots ([MAR research](https://arxiv.org/html/2512.20845)), the validation worker contributes to reflection:

```
Implementation worker completes
        │
        ▼
Validation worker reviews
        │
        ├─ Generates independent assessment
        │   └─ "Model struggled with X, succeeded at Y"
        │
        └─ Both perspectives stored in reasoning bank
```

#### Configuration

```toml
[model_routing]
# Static heuristics as cold start
use_static_heuristics = true

# Learning from experience
enable_learning = true
min_samples_for_learning = 10
similarity_threshold = 0.7

# Reflection generation
generate_reflections = true
reflection_model = "claude-haiku"  # Cheap model for reflections

# Blend weights (when enough data exists)
static_weight = 0.3
learned_weight = 0.7
```

#### Benefits Over Pure Static

| Static Only | With Reflexion |
|-------------|----------------|
| Fixed rules forever | Adapts to model improvements/regressions |
| All "auth" tasks treated equal | Learns nuances (auth + migration = hard) |
| No project-specific learning | Learns your codebase patterns |
| Same mistakes repeated | Avoids past failure modes |

## 12. Observability (Single Worker Per Bead)

**Decision: One worker per bead at a time. TDD within worker. Post-completion review.**

### Concurrency Model

```
Bead: bd-a3f8.1
      │
      ├─ Worker: claude-code-1 (EXCLUSIVE)
      │   ├─ Implements
      │   ├─ Tests (TDD)
      │   ├─ Commits
      │   └─ Releases bead
      │
      ▼
Bead: bd-a3f8.1 (status: review)
      │
      └─ Worker: review-bot (EXCLUSIVE)
          ├─ Validates
          ├─ Checks deployed artifacts
          └─ Approves or returns
```

No two workers touch the same bead simultaneously. This eliminates:
- Merge conflicts within a bead
- Race conditions on test state
- Confusion about ownership

## 13. Resilience & Self-Improvement Safety

**Decision: Canary deploys, automatic rollback, staging environment.**

### Research Findings

From [agent versioning best practices](https://www.gofast.ai/blog/agent-versioning-rollbacks):
- "Versioning and rollback aren't nice-to-haves—they're survival tools"
- Canary deployments reduce blast radius
- Automated rollback minimizes recovery time

### Self-Improvement Pipeline (Local)

Ringmaster self-improvement deploys **locally to the workspace server**, not to K8s:

```
Ringmaster improvement task
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. Worker implements change in staging branch                       │
│  2. Full test suite runs (pytest, npm test)                          │
│  3. If tests pass:                                                   │
│     └─ Hot-reload affected component (uvicorn, vite)                │
│  4. Monitor for N minutes:                                           │
│     ├─ No errors in logs → Keep changes                             │
│     └─ Errors detected → Git revert + restart                       │
│  5. If stable:                                                       │
│     └─ Merge to main                                                │
└─────────────────────────────────────────────────────────────────────┘

This is LOCAL process restarts, not K8s deployments.
```

### Project Deployments (K8s)

When workers need to test **project code** that requires secrets or integration:

```
Project code needs deployment testing
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. Worker creates/updates deployment manifests                      │
│  2. Ringmaster triggers deploy to K8s staging namespace             │
│     └─ kubectl apply -n staging                                     │
│  3. Sealed secrets decrypted by cluster                              │
│  4. Worker runs integration tests against staging                    │
│     └─ curl, API calls, E2E tests                                   │
│  5. Results determine task success/failure                           │
│  6. Staging namespace cleaned up                                     │
└─────────────────────────────────────────────────────────────────────┘

This is K8s deployment to an associated cluster.
```

### Two Deployment Targets

| What | Where | When |
|------|-------|------|
| Ringmaster itself | Local (process restart) | Self-improvement tasks |
| Project services | K8s staging namespace | Integration testing, secrets needed |

### Rollback Triggers

| Metric | Threshold | Action |
|--------|-----------|--------|
| Error rate | > 5% | Rollback |
| Response latency | > 2x baseline | Rollback |
| Test failures | Any | Rollback |
| Worker crashes | > 1 | Rollback |

### Additional Resilience Measures

1. **Immutable releases**: Every deploy is a tagged git commit
2. **State snapshots**: SQLite backups before any self-modification
3. **Circuit breakers**: Disable self-improvement if 3 consecutive failures
4. **Human approval gate**: Major changes require user confirmation
5. **Diff review**: All self-modifications shown to user before merge

## 14. Deployment Model

**Decision: Remote server/VPS. User connects to access Ringmaster.**

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  USER DEVICE                                                         │
│  ├─ Browser → Ringmaster UI (https://ringmaster.example.com)        │
│  └─ SSH → Direct server access if needed                            │
└─────────────────────────────────────────────────────────────────────┘
            │
            │ HTTPS / WSS
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  REMOTE SERVER / VPS                                                 │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  RINGMASTER                                                     ││
│  │  ├─ API Server (FastAPI)                                        ││
│  │  ├─ Queue Manager                                               ││
│  │  ├─ Enricher                                                    ││
│  │  ├─ Scheduler                                                   ││
│  │  └─ Worker Containers                                           ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  WORKSPACE                                                       ││
│  │  ├─ /workspace/project-a/                                       ││
│  │  ├─ /workspace/project-b/                                       ││
│  │  └─ /workspace/project-a.worktrees/                             ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  STATE                                                           ││
│  │  ├─ SQLite database                                             ││
│  │  └─ File storage                                                ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Open Architecture Summary

| Question | Decision |
|----------|----------|
| Sync vs Async | **Async** - User updates context, workers pull and process |
| Stateful vs Stateless | **Stateless** - Fresh start, artifacts in bead for resumption |
| Single vs Distributed | **Single server** - Vertical scaling for now |
| Push vs Pull | **Pull** - Workers pull highest-priority capable bead |
| Monorepo vs Multi-repo | **Both** - Workspace contains multiple repos |

## Workspace Hierarchy

```
/workspace/                          # Root workspace
├── repo-a/                          # Monorepo with manifests + code
│   ├── src/
│   ├── deploy/
│   └── .beads/
├── repo-b/                          # Simple code repo
│   ├── src/
│   └── .beads/
├── repo-a.worktrees/                # Worktrees for repo-a
│   ├── worker-1/
│   └── worker-2/
└── repo-b.worktrees/                # Worktrees for repo-b
    └── worker-3/

Relationships:
- Workspace has multiple repositories
- Repositories have multiple beads
- Beads are worked on by multiple workers (sequentially, not concurrently)
- One worker per bead at any time
```
