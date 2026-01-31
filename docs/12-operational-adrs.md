# Operational Architecture Decision Records

## Overview

These ADRs address operational concerns: scaling, quotas, knowledge management, and user experience.

---

## ADR-013: Worker Scaling Policy

**Status:** Proposed
**Context:** How many workers should run? When to scale up/down?

### Decision

Implement **queue-depth based autoscaling** with configurable bounds.

### Scaling Algorithm

```python
class WorkerScaler:
    """Autoscales worker pool based on queue depth."""

    def __init__(self, config: ScalingConfig):
        self.config = config
        self.min_workers = config.min_workers  # 1
        self.max_workers = config.max_workers  # 10
        self.target_queue_per_worker = config.target_queue_per_worker  # 2

    async def evaluate(self) -> ScalingDecision:
        """Evaluate whether to scale up/down."""

        current_workers = await self._count_active_workers()
        queue_depth = await self._get_queue_depth()
        idle_workers = await self._count_idle_workers()

        # Calculate desired workers
        desired = max(
            self.min_workers,
            min(
                self.max_workers,
                queue_depth // self.target_queue_per_worker + 1
            )
        )

        if desired > current_workers:
            # Scale up
            to_add = min(
                desired - current_workers,
                self.config.max_scale_up_per_cycle,  # 2
            )
            return ScalingDecision(
                action="scale_up",
                count=to_add,
                reason=f"Queue depth {queue_depth} > {current_workers * self.target_queue_per_worker}",
            )

        elif desired < current_workers and idle_workers > 0:
            # Scale down (only idle workers)
            to_remove = min(
                current_workers - desired,
                idle_workers,
                self.config.max_scale_down_per_cycle,  # 1
            )

            # Cooldown check
            if await self._in_cooldown():
                return ScalingDecision(action="none", reason="In cooldown period")

            return ScalingDecision(
                action="scale_down",
                count=to_remove,
                reason=f"{idle_workers} idle workers, queue depth {queue_depth}",
            )

        return ScalingDecision(action="none", reason="At optimal scale")

    async def apply(self, decision: ScalingDecision) -> None:
        """Apply scaling decision."""

        if decision.action == "scale_up":
            for _ in range(decision.count):
                worker_type = self._select_worker_type()
                await spawner.spawn(
                    worker_id=generate_worker_id(),
                    worker_type=worker_type,
                )
            logger.info(f"Scaled up {decision.count} workers: {decision.reason}")

        elif decision.action == "scale_down":
            idle = await self._get_idle_workers()
            for worker in idle[:decision.count]:
                await spawner.kill(worker.id)
            logger.info(f"Scaled down {decision.count} workers: {decision.reason}")
```

### Configuration

```toml
[scaling]
enabled = true
min_workers = 1
max_workers = 10
target_queue_per_worker = 2

# Rate limiting
max_scale_up_per_cycle = 2
max_scale_down_per_cycle = 1
cooldown_seconds = 300  # 5 min between scale-down

# Worker type preferences
[scaling.preferences]
default_type = "claude-code"
high_priority_type = "claude-code"  # Use for P0 beads
low_priority_type = "claude-code"   # Could use cheaper model
```

---

## ADR-014: Rate Limiting and Quotas

**Status:** Proposed
**Context:** Prevent runaway API costs and resource exhaustion.

### Decision

Implement **tiered rate limits** at project, worker, and global levels.

### Rate Limit Tiers

```python
@dataclass
class RateLimits:
    """Rate limits at different scopes."""

    # Global limits
    global_requests_per_minute: int = 100
    global_tokens_per_hour: int = 10_000_000
    global_cost_per_day_usd: float = 500.0

    # Per-project limits
    project_requests_per_minute: int = 20
    project_tokens_per_hour: int = 2_000_000
    project_cost_per_day_usd: float = 100.0

    # Per-worker limits
    worker_requests_per_minute: int = 10
    worker_consecutive_failures: int = 5  # Circuit breaker

class RateLimiter:
    """Multi-tier rate limiter."""

    def __init__(self, limits: RateLimits, db: Database):
        self.limits = limits
        self.db = db

    async def check(self, worker_id: str, project_id: str) -> RateLimitResult:
        """Check if request is allowed."""

        checks = [
            await self._check_global(),
            await self._check_project(project_id),
            await self._check_worker(worker_id),
        ]

        for check in checks:
            if not check.allowed:
                return check

        return RateLimitResult(allowed=True)

    async def _check_global(self) -> RateLimitResult:
        # Check requests/minute
        recent_requests = await self.db.count_requests(minutes=1)
        if recent_requests >= self.limits.global_requests_per_minute:
            return RateLimitResult(
                allowed=False,
                reason="Global request limit reached",
                retry_after_seconds=60,
            )

        # Check tokens/hour
        recent_tokens = await self.db.sum_tokens(hours=1)
        if recent_tokens >= self.limits.global_tokens_per_hour:
            return RateLimitResult(
                allowed=False,
                reason="Global token limit reached",
                retry_after_seconds=3600,
            )

        # Check cost/day
        today_cost = await self.db.sum_cost(hours=24)
        if today_cost >= self.limits.global_cost_per_day_usd:
            return RateLimitResult(
                allowed=False,
                reason=f"Daily cost limit ${self.limits.global_cost_per_day_usd} reached",
                retry_after_seconds=self._seconds_until_midnight(),
            )

        return RateLimitResult(allowed=True)

    async def record(self, request: RequestMetrics) -> None:
        """Record a completed request for rate limiting."""
        await self.db.insert_request_metrics(request)
```

### Cost Dashboard

```python
async def get_cost_summary() -> CostSummary:
    """Get cost summary for dashboard."""

    return CostSummary(
        today=await db.sum_cost(hours=24),
        this_week=await db.sum_cost(hours=168),
        this_month=await db.sum_cost(hours=720),

        by_project=await db.sum_cost_by_project(hours=24),
        by_worker=await db.sum_cost_by_worker(hours=24),
        by_model=await db.sum_cost_by_model(hours=24),

        limit_today=config.global_cost_per_day_usd,
        remaining_today=config.global_cost_per_day_usd - await db.sum_cost(hours=24),
    )
```

---

## ADR-015: Research & Knowledge Persistence

**Status:** Proposed
**Context:** Workers do research that's lost after task completion. Same questions get re-researched.

### Decision

Persist research to **project knowledge base** for reuse.

### Knowledge Types

```python
class KnowledgeType(str, Enum):
    RESEARCH = "research"           # Web search results, documentation
    DECISION = "decision"           # Architectural decisions made
    PATTERN = "pattern"             # Discovered code patterns
    CONVENTION = "convention"       # Project conventions learned
    DEPENDENCY = "dependency"       # Dependency information
    API = "api"                     # External API details

@dataclass
class KnowledgeEntry:
    id: str
    project_id: str
    type: KnowledgeType
    title: str
    content: str
    source: str                     # "worker:claude-1" or "user" or "web:url"
    keywords: list[str]
    created_at: datetime
    accessed_at: datetime
    access_count: int = 0
    relevance_score: float = 1.0    # Decays over time, boosted on access
```

### Knowledge Capture

Workers are prompted to emit knowledge:

```markdown
## Knowledge Capture

When you discover something useful for future tasks, emit it:

```xml
<knowledge type="pattern" title="Auth middleware pattern">
This project uses a decorator pattern for auth:
@require_auth(roles=["admin"])
def protected_endpoint(): ...
</knowledge>

<knowledge type="convention" title="Error handling">
All API errors should use the ApiError class with error codes from errors.py
</knowledge>
```

These will be stored and made available to future workers on this project.
```

### Knowledge Injection

```python
async def enrich_with_knowledge(bead: Bead, prompt: str) -> str:
    """Inject relevant knowledge into prompt."""

    # Extract keywords from bead
    bead_keywords = extract_keywords(bead)

    # Find relevant knowledge
    relevant = await knowledge_repo.search(
        project_id=bead.project_id,
        keywords=bead_keywords,
        limit=10,
    )

    if not relevant:
        return prompt

    knowledge_section = "\n## Project Knowledge\n\n"
    for entry in relevant:
        knowledge_section += f"### {entry.title} ({entry.type.value})\n"
        knowledge_section += f"{entry.content}\n\n"

        # Boost relevance score
        await knowledge_repo.record_access(entry.id)

    return prompt + knowledge_section
```

### Knowledge Decay

```python
async def decay_knowledge():
    """Periodically decay unused knowledge relevance."""

    # Entries not accessed in 30 days decay by 10%
    await db.execute(
        """
        UPDATE knowledge
        SET relevance_score = relevance_score * 0.9
        WHERE accessed_at < datetime('now', '-30 days')
          AND relevance_score > 0.1
        """
    )

    # Remove entries with very low relevance
    await db.execute(
        """
        DELETE FROM knowledge
        WHERE relevance_score < 0.1
          AND accessed_at < datetime('now', '-90 days')
        """
    )
```

---

## ADR-016: User Notification & Escalation

**Status:** Proposed
**Context:** Users need to know when attention is required without constant monitoring.

### Decision

Implement **multi-channel notifications** with escalation policies.

### Notification Channels

```python
class NotificationChannel(str, Enum):
    UI = "ui"                   # In-app notification
    WEBSOCKET = "websocket"     # Real-time push
    EMAIL = "email"             # Email notification
    SLACK = "slack"             # Slack webhook
    WEBHOOK = "webhook"         # Generic webhook

@dataclass
class NotificationConfig:
    channels: list[NotificationChannel]
    urgency: str  # "low", "normal", "high", "critical"
    dedupe_key: str | None = None  # Prevent duplicate notifications
    escalate_after_minutes: int | None = None
```

### Notification Types

```python
NOTIFICATION_CONFIGS = {
    "decision_needed": NotificationConfig(
        channels=[NotificationChannel.UI, NotificationChannel.WEBSOCKET],
        urgency="high",
        escalate_after_minutes=30,
    ),
    "task_completed": NotificationConfig(
        channels=[NotificationChannel.UI],
        urgency="low",
    ),
    "task_failed": NotificationConfig(
        channels=[NotificationChannel.UI, NotificationChannel.WEBSOCKET],
        urgency="normal",
    ),
    "circuit_breaker_tripped": NotificationConfig(
        channels=[NotificationChannel.UI, NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL],
        urgency="critical",
    ),
    "cost_limit_warning": NotificationConfig(
        channels=[NotificationChannel.UI, NotificationChannel.EMAIL],
        urgency="high",
        dedupe_key="cost_warning_today",
    ),
}
```

### Escalation Policy

```python
class EscalationManager:
    """Manages notification escalation."""

    async def check_escalations(self) -> None:
        """Check for notifications needing escalation."""

        # Find unacknowledged notifications past escalation time
        pending = await db.fetch_all(
            """
            SELECT * FROM notifications
            WHERE acknowledged_at IS NULL
              AND escalate_after IS NOT NULL
              AND created_at < datetime('now', '-' || escalate_after_minutes || ' minutes')
              AND escalated_at IS NULL
            """
        )

        for notification in pending:
            await self._escalate(notification)

    async def _escalate(self, notification: Notification) -> None:
        """Escalate a notification to additional channels."""

        # Add email if not already included
        if NotificationChannel.EMAIL not in notification.channels:
            await self._send_email(notification)

        # Mark as escalated
        await db.execute(
            "UPDATE notifications SET escalated_at = ? WHERE id = ?",
            (datetime.now(UTC), notification.id)
        )

        logger.warning(f"Escalated notification {notification.id}: {notification.title}")
```

### Notification Batching

```python
class NotificationBatcher:
    """Batches low-urgency notifications to reduce noise."""

    async def queue(self, notification: Notification) -> None:
        if notification.urgency == "low":
            # Batch low-urgency notifications
            await self._add_to_batch(notification)
        else:
            # Send immediately
            await self._send(notification)

    async def flush_batch(self) -> None:
        """Send batched notifications (run every 15 min)."""
        batch = await self._get_batch()

        if len(batch) == 0:
            return

        if len(batch) == 1:
            await self._send(batch[0])
        else:
            # Combine into digest
            digest = self._create_digest(batch)
            await self._send(digest)

        await self._clear_batch()
```

---

## ADR-017: Context Window Management

**Status:** Proposed
**Context:** Long tasks exhaust context windows, causing degradation.

### Decision

Implement **proactive context management** with summarization and windowing.

### Context Budget

```python
@dataclass
class ContextBudget:
    """Token budget allocation for prompt assembly."""

    total: int = 180_000  # Leave room for response

    # Allocation
    system_prompt: int = 2_000
    task_description: int = 5_000
    code_context: int = 50_000
    history: int = 30_000
    knowledge: int = 10_000
    messages: int = 5_000
    reserved: int = 78_000  # For worker's use

    def allocate(self, sections: dict[str, str]) -> dict[str, str]:
        """Allocate tokens to sections, summarizing if needed."""
        result = {}

        for section, content in sections.items():
            budget = getattr(self, section, 10_000)
            tokens = count_tokens(content)

            if tokens <= budget:
                result[section] = content
            else:
                # Summarize to fit budget
                result[section] = summarize_to_tokens(content, budget)

        return result
```

### Sliding Window for Long Tasks

```python
class ContextWindow:
    """Manages context window for long-running tasks."""

    def __init__(self, max_history_turns: int = 20):
        self.max_history_turns = max_history_turns

    async def prepare_context(self, bead: Bead, iteration: int) -> PreparedContext:
        """Prepare context for iteration, managing window."""

        history = await self._get_history(bead.id)

        if len(history) > self.max_history_turns:
            # Summarize older history
            old_history = history[:-self.max_history_turns]
            recent_history = history[-self.max_history_turns:]

            summary = await self._summarize_history(old_history)

            return PreparedContext(
                history_summary=summary,
                recent_history=recent_history,
                iteration=iteration,
            )

        return PreparedContext(
            history_summary=None,
            recent_history=history,
            iteration=iteration,
        )

    async def _summarize_history(self, history: list[HistoryEntry]) -> str:
        """Summarize old history to preserve key information."""

        prompt = f"""
Summarize this conversation history, preserving:
- Key decisions made
- Errors encountered and how they were resolved
- Important discoveries about the codebase
- Current state of the implementation

History:
{format_history(history)}

Summary (be concise):
"""
        return await llm.complete(prompt, model="claude-haiku-4-20250514")
```

### Degradation Detection

```python
async def detect_context_degradation(output: str, history: list[str]) -> bool:
    """Detect if worker is showing signs of context degradation."""

    signals = {
        # Repetition
        "repeating_phrases": count_repeated_phrases(output, history) > 3,

        # Forgetting constraints
        "apologizing": output.count("I apologize") > 2,
        "contradicting": detects_contradiction(output, history),

        # Going in circles
        "similar_to_recent": any(
            similarity(output, h) > 0.8
            for h in history[-5:]
        ),
    }

    degraded = sum(signals.values()) >= 2

    if degraded:
        logger.warning(f"Context degradation detected: {signals}")

    return degraded
```

---

## ADR-018: Audit Logging

**Status:** Proposed
**Context:** Need audit trail for debugging, compliance, and learning.

### Decision

Log all significant events to an **append-only audit log**.

### Audit Events

```python
class AuditEventType(str, Enum):
    # Bead lifecycle
    BEAD_CREATED = "bead.created"
    BEAD_ASSIGNED = "bead.assigned"
    BEAD_COMPLETED = "bead.completed"
    BEAD_FAILED = "bead.failed"

    # Worker lifecycle
    WORKER_SPAWNED = "worker.spawned"
    WORKER_KILLED = "worker.killed"
    WORKER_CRASHED = "worker.crashed"

    # Execution
    ITERATION_STARTED = "iteration.started"
    ITERATION_COMPLETED = "iteration.completed"
    CHECKPOINT_CREATED = "checkpoint.created"

    # Decisions
    DECISION_REQUESTED = "decision.requested"
    DECISION_MADE = "decision.made"

    # Self-improvement
    SELF_IMPROVEMENT_STARTED = "self.started"
    SELF_IMPROVEMENT_VALIDATED = "self.validated"
    SELF_IMPROVEMENT_APPLIED = "self.applied"
    SELF_IMPROVEMENT_ROLLED_BACK = "self.rolled_back"

    # System
    RATE_LIMIT_HIT = "ratelimit.hit"
    CIRCUIT_BREAKER_TRIPPED = "circuit.tripped"
    CONFIG_CHANGED = "config.changed"

@dataclass
class AuditEvent:
    id: str
    timestamp: datetime
    type: AuditEventType
    actor: str  # worker_id, "user", "system"
    resource_type: str  # "bead", "worker", "project"
    resource_id: str
    details: dict
    metadata: dict = field(default_factory=dict)
```

### Audit Logger

```python
class AuditLogger:
    """Append-only audit logger."""

    def __init__(self, db: Database):
        self.db = db

    async def log(
        self,
        event_type: AuditEventType,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: dict,
        metadata: dict | None = None,
    ) -> str:
        """Log an audit event."""

        event = AuditEvent(
            id=generate_id(),
            timestamp=datetime.now(UTC),
            type=event_type,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            metadata=metadata or {},
        )

        # Append-only insert
        await self.db.execute(
            """
            INSERT INTO audit_log (id, timestamp, type, actor, resource_type, resource_id, details, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event.id, event.timestamp, event.type.value, event.actor,
             event.resource_type, event.resource_id,
             json.dumps(event.details), json.dumps(event.metadata))
        )

        return event.id

    async def query(
        self,
        resource_id: str | None = None,
        event_types: list[AuditEventType] | None = None,
        actor: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query audit log."""

        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []

        if resource_id:
            query += " AND resource_id = ?"
            params.append(resource_id)

        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query += f" AND type IN ({placeholders})"
            params.extend([t.value for t in event_types])

        if actor:
            query += " AND actor = ?"
            params.append(actor)

        if since:
            query += " AND timestamp >= ?"
            params.append(since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(query, params)
        return [AuditEvent(**row) for row in rows]
```

### Audit Integration

```python
# Decorator for automatic audit logging
def audited(event_type: AuditEventType, resource_type: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Extract resource_id from result or kwargs
            resource_id = getattr(result, "id", None) or kwargs.get("id")

            await audit_logger.log(
                event_type=event_type,
                actor=get_current_actor(),
                resource_type=resource_type,
                resource_id=resource_id,
                details={"args": str(args), "kwargs": str(kwargs)},
            )

            return result
        return wrapper
    return decorator

# Usage
@audited(AuditEventType.BEAD_CREATED, "bead")
async def create_bead(title: str, description: str, ...) -> Bead:
    ...
```

---

## Summary: Operational ADRs

| ADR | Purpose | Key Mechanism |
|-----|---------|---------------|
| **ADR-013** | Worker scaling | Queue-depth autoscaling with bounds |
| **ADR-014** | Cost control | Tiered rate limits (global/project/worker) |
| **ADR-015** | Knowledge reuse | Persistent knowledge base with decay |
| **ADR-016** | User attention | Multi-channel notifications with escalation |
| **ADR-017** | Long task support | Context windowing and summarization |
| **ADR-018** | Debugging/compliance | Append-only audit log |

### Configuration Summary

```toml
[scaling]
enabled = true
min_workers = 1
max_workers = 10

[rate_limits]
global_cost_per_day_usd = 500.0
project_cost_per_day_usd = 100.0

[knowledge]
enabled = true
decay_after_days = 30

[notifications]
channels = ["ui", "websocket"]
escalate_after_minutes = 30

[context]
max_history_turns = 20
summarize_threshold_tokens = 50000

[audit]
enabled = true
retention_days = 90
```
