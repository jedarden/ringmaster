# Context Enrichment

## Overview

Context enrichment is **source-based, not stage-based**. Ringmaster assembles context by pulling from relevant sources based on the task at hand—not every task needs every source.

## Context Sources

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONTEXT SOURCES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  CONVERSATION   │  │    RESEARCH     │  │  DOCUMENTATION  │             │
│  │                 │  │                 │  │                 │             │
│  │ • Chat history  │  │ • Prior agent   │  │ • Project goals │             │
│  │ • Decisions     │  │   outputs       │  │ • ADRs          │             │
│  │ • User prefs    │  │ • Web searches  │  │ • Conventions   │             │
│  │                 │  │ • Fetched docs  │  │ • API specs     │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┼────────────────────┘                       │
│                                │                                            │
│                                ▼                                            │
│                    ┌───────────────────────┐                                │
│                    │   CONTEXT ASSEMBLER   │                                │
│                    │                       │                                │
│                    │  • Relevance scoring  │                                │
│                    │  • Token budgeting    │                                │
│                    │  • RLM compression    │                                │
│                    └───────────┬───────────┘                                │
│                                │                                            │
│           ┌────────────────────┼────────────────────┐                       │
│           │                    │                    │                       │
│  ┌────────┴────────┐  ┌────────┴────────┐  ┌────────┴────────┐             │
│  │      CODE       │  │   DEPLOYMENT    │  │      LOGS       │             │
│  │                 │  │                 │  │                 │             │
│  │ • Source files  │  │ • Env configs   │  │ • Service logs  │             │
│  │ • Type defs     │  │ • K8s manifests │  │ • Error traces  │             │
│  │ • Test examples │  │ • CI/CD status  │  │ • Metrics       │             │
│  │                 │  │ • Infra state   │  │ • Audit trail   │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Source Definitions

### 1. Conversation

Prior interactions within this project.

| Content | When Relevant | Compression |
|---------|---------------|-------------|
| Recent messages (last N) | Always | None (verbatim) |
| Older messages | When referenced | RLM summary |
| User decisions | When topic overlaps | Extract & preserve |
| User preferences | Always | Compact list |

**Example:** User previously said "use 24h token expiry" → must be in context when working on auth.

### 2. Research Outputs

Results from prior agent work or explicit research tasks.

| Content | When Relevant | Compression |
|---------|---------------|-------------|
| Agent task outputs | When task is related | RLM summary |
| Web search results | When topic matches | Key excerpts |
| Fetched documentation | When library/API mentioned | Relevant sections |
| Spike/exploration results | When informing design | Conclusions only |

**Example:** An agent previously researched "JWT best practices" → that output is available for auth tasks.

### 3. Documentation

Project-level knowledge that persists.

| Content | When Relevant | Compression |
|---------|---------------|-------------|
| Project description | Always | None |
| Goals / roadmap | When planning | None |
| ADRs | When topic matches | Full or summary |
| Coding conventions | Always | None |
| API specifications | When API-related | Relevant endpoints |
| Library docs | When library used | Relevant sections |

**Example:** ADR-001 says "use RS256 for JWTs" → included for any auth work.

### 4. Code

Source files from the codebase.

| Content | When Relevant | Compression |
|---------|---------------|-------------|
| Explicitly mentioned files | Always | None |
| Semantically related files | Score > threshold | None or summary |
| Import dependencies | When modifying file | None |
| Type definitions | When types referenced | None |
| Test examples | When writing tests | Relevant tests |
| Recent changes | When debugging | Diff only |

**Example:** User mentions "auth module" → include `src/auth/*.rs` and related types.

### 5. Deployment

Infrastructure and environment context.

| Content | When Relevant | Compression |
|---------|---------------|-------------|
| Environment configs | When env-specific | Relevant vars |
| K8s manifests | When infra-related | Relevant resources |
| CI/CD pipeline status | When build/deploy issue | Recent runs |
| Infrastructure state | When debugging infra | Current state |
| Secrets (names only) | When auth/config issue | Names, not values |

**Example:** Debugging "works locally, fails in prod" → need deployment configs.

### 6. Logs

Runtime information from services.

| Content | When Relevant | Compression |
|---------|---------------|-------------|
| Error logs | When debugging error | Recent + filtered |
| Service logs | When investigating behavior | Filtered window |
| Stack traces | When debugging crash | Full trace |
| Metrics/APM | When performance issue | Relevant graphs/data |
| Audit trail | When tracking changes | Relevant entries |

**Example:** User reports "500 error on login" → need recent error logs for auth service.

## Relevance Scoring

Not everything is relevant. Each source scores content for inclusion:

```python
def score_relevance(content: Content, task: Task) -> float:
    """Score 0.0 to 1.0 for relevance to task."""

    score = 0.0

    # Semantic similarity to task description
    semantic = embedding_similarity(content.text, task.description)
    score += semantic * 0.4

    # Keyword overlap
    keywords = extract_keywords(task.description)
    keyword_hits = count_keyword_matches(content.text, keywords)
    score += min(keyword_hits / 5, 1.0) * 0.3

    # Recency (for logs, conversation)
    if content.timestamp:
        age_hours = (now() - content.timestamp).hours
        recency = max(0, 1 - (age_hours / 168))  # Decay over 1 week
        score += recency * 0.2

    # Explicit reference (mentioned by name)
    if content.name in task.description:
        score += 0.3

    return min(score, 1.0)
```

### Inclusion Thresholds

```toml
[enrichment.thresholds]
conversation = 0.3      # Low bar - usually relevant
research = 0.5          # Medium - must be related
documentation = 0.4     # Medium-low - ADRs often helpful
code = 0.5              # Medium - avoid noise
deployment = 0.6        # Higher - only when clearly needed
logs = 0.7              # High - must be debugging
```

## RLM Compression

When content exceeds budget, RLM compresses it:

```python
def compress_if_needed(content: str, budget_tokens: int) -> str:
    """Compress content to fit budget while preserving key information."""

    current_tokens = count_tokens(content)

    if current_tokens <= budget_tokens:
        return content  # Fits, no compression needed

    # Compression ratio needed
    ratio = budget_tokens / current_tokens

    if ratio > 0.7:
        # Light compression - remove boilerplate
        return remove_boilerplate(content)

    elif ratio > 0.3:
        # Medium compression - summarize sections
        return summarize_sections(content, target_tokens=budget_tokens)

    else:
        # Heavy compression - extract key points only
        return extract_key_points(content, target_tokens=budget_tokens)
```

### Compression Strategies by Source

| Source | Light | Medium | Heavy |
|--------|-------|--------|-------|
| Conversation | Remove timestamps | Summarize old messages | Key decisions only |
| Research | Remove examples | Summarize findings | Conclusions only |
| Documentation | Remove formatting | Summarize sections | Key points only |
| Code | Remove comments | Summarize functions | Signatures only |
| Deployment | Remove defaults | Summarize configs | Diff from default |
| Logs | Remove noise | Summarize patterns | Errors only |

## Context Assembly

The assembler pulls from sources and fits to budget:

```python
def assemble_context(task: Task, budget_tokens: int) -> Context:
    """Assemble context from relevant sources within token budget."""

    # 1. Collect candidates from all sources
    candidates = []

    for source in SOURCES:
        items = source.query(task)
        for item in items:
            score = score_relevance(item, task)
            if score >= source.threshold:
                candidates.append((item, score, source))

    # 2. Sort by relevance
    candidates.sort(key=lambda x: x[1], reverse=True)

    # 3. Allocate budget by priority
    budget_remaining = budget_tokens
    included = []

    # Always include (fixed budget)
    fixed = get_fixed_context(task)  # Task description, project basics
    budget_remaining -= count_tokens(fixed)
    included.append(fixed)

    # Include by relevance until budget exhausted
    for item, score, source in candidates:
        item_tokens = count_tokens(item.content)

        if item_tokens <= budget_remaining:
            # Fits - include as-is
            included.append(item)
            budget_remaining -= item_tokens

        elif budget_remaining > 500:
            # Doesn't fit - try compression
            compressed = compress_if_needed(item.content, budget_remaining - 100)
            if compressed:
                included.append(item.with_content(compressed))
                budget_remaining -= count_tokens(compressed)

        if budget_remaining < 500:
            break  # Leave headroom for worker

    return Context(items=included, tokens_used=budget_tokens - budget_remaining)
```

## Task-Specific Assembly

Different tasks need different sources:

### Bug Fix Task
```
Sources prioritized:
├── Logs (error traces, recent logs)      HIGH
├── Code (affected files, related tests)  HIGH
├── Conversation (bug report details)     MEDIUM
├── Deployment (if env-specific)          MEDIUM
├── Documentation (relevant ADRs)         LOW
└── Research                              LOW
```

### New Feature Task
```
Sources prioritized:
├── Documentation (goals, ADRs, specs)    HIGH
├── Conversation (requirements)           HIGH
├── Code (related modules, patterns)      HIGH
├── Research (prior spikes, web docs)     MEDIUM
├── Deployment                            LOW
└── Logs                                  LOW
```

### Infrastructure Task
```
Sources prioritized:
├── Deployment (configs, manifests)       HIGH
├── Logs (service health, errors)         HIGH
├── Documentation (infra ADRs)            MEDIUM
├── Code (infra-as-code)                  MEDIUM
├── Conversation                          LOW
└── Research                              LOW
```

### Research Task
```
Sources prioritized:
├── Research (prior findings)             HIGH
├── Documentation (goals, constraints)    HIGH
├── Conversation (research questions)     MEDIUM
├── Code (if exploring codebase)          MEDIUM
├── Deployment                            LOW
└── Logs                                  LOW
```

## Configuration

```toml
# ringmaster.toml

[enrichment]
# Global settings
default_budget_tokens = 24000
min_headroom_tokens = 4000

[enrichment.sources.conversation]
enabled = true
threshold = 0.3
max_tokens = 4000
recent_messages_verbatim = 10
compress_older = true

[enrichment.sources.research]
enabled = true
threshold = 0.5
max_tokens = 4000
include_web_searches = true
include_agent_outputs = true

[enrichment.sources.documentation]
enabled = true
threshold = 0.4
max_tokens = 3000
always_include = ["project.md", "conventions.md"]

[enrichment.sources.code]
enabled = true
threshold = 0.5
max_tokens = 12000
include_types = true
include_tests = true
include_imports = true

[enrichment.sources.deployment]
enabled = true
threshold = 0.6
max_tokens = 2000
include_env_configs = true
include_k8s = true
redact_secrets = true

[enrichment.sources.logs]
enabled = true
threshold = 0.7
max_tokens = 3000
log_window_hours = 24
filter_noise = true
```

## Source Adapters

Each source has an adapter that knows how to query and format content:

```python
class SourceAdapter(Protocol):
    name: str
    threshold: float

    def query(self, task: Task) -> list[Content]:
        """Return candidate content items for this task."""
        ...

    def compress(self, content: str, target_tokens: int) -> str:
        """Compress content to fit target token budget."""
        ...

class ConversationSource(SourceAdapter):
    name = "conversation"
    threshold = 0.3

    def query(self, task: Task) -> list[Content]:
        messages = db.get_messages(project_id=task.project_id)
        recent = messages[-self.recent_verbatim:]
        older = messages[:-self.recent_verbatim]

        return [
            Content(type="recent_messages", content=format_messages(recent)),
            Content(type="older_messages", content=format_messages(older)),
            Content(type="decisions", content=extract_decisions(messages)),
        ]

class LogsSource(SourceAdapter):
    name = "logs"
    threshold = 0.7

    def query(self, task: Task) -> list[Content]:
        # Only query logs if task looks like debugging
        if not self.is_debugging_task(task):
            return []

        logs = log_aggregator.query(
            service=task.infer_service(),
            hours=self.log_window_hours,
            level="error"
        )

        return [Content(type="error_logs", content=format_logs(logs))]
```

## Incremental Updates

Context sources are cached and updated incrementally:

```python
class ContextCache:
    """Cache for expensive-to-compute context."""

    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds

    def get_or_compute(self, key: str, compute_fn: Callable) -> Content:
        if key in self.cache:
            entry = self.cache[key]
            if entry.age_seconds < self.ttl:
                return entry.content

        content = compute_fn()
        self.cache[key] = CacheEntry(content=content, timestamp=now())
        return content

# Usage
cache = ContextCache(ttl_seconds=300)

def get_code_context(task: Task) -> Content:
    key = f"code:{task.project_id}:{hash(task.description)}"
    return cache.get_or_compute(key, lambda: compute_code_context(task))
```

## Observability

Track what context is being assembled:

```python
@dataclass
class ContextAssemblyLog:
    task_id: str
    sources_queried: list[str]
    candidates_found: int
    items_included: int
    tokens_used: int
    tokens_budget: int
    compression_applied: list[str]
    assembly_time_ms: int

# Log every assembly for debugging and improvement
def log_assembly(log: ContextAssemblyLog):
    db.insert("context_assembly_logs", log)

    # Alert if consistently hitting budget limits
    if log.tokens_used > log.tokens_budget * 0.95:
        alert("Context assembly near budget limit", log)
```
