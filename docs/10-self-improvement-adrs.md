# Self-Improvement Architecture Decision Records

## Overview

This document captures the additional ADRs needed to enable Ringmaster to improve itself. These build on the foundations in `06-deployment.md` (flywheel) and `08-open-architecture.md` (safety rails).

---

## ADR-001: Self-Observation & Problem Detection

**Status:** Proposed
**Context:** Ringmaster can't improve itself if it doesn't know what's wrong.

### Decision

Ringmaster maintains a **self-observation system** that identifies improvement opportunities from operational data.

### Problem Detection Sources

| Source | What It Detects | Example |
|--------|-----------------|---------|
| **Reasoning Bank** | Repeated failures for task types | "Auth tasks fail 60% with Haiku" |
| **Worker Metrics** | Slow/failing patterns | "Enricher takes >30s for large projects" |
| **Error Logs** | Recurring exceptions | "KeyError in routing.py:142 (5x today)" |
| **User Feedback** | Blocked tasks, manual overrides | "User rejected 3 model selections" |
| **Cost Metrics** | Inefficient spending | "Opus used for simple renames" |

### Implementation

```python
class SelfObserver:
    """Observes Ringmaster's own behavior and identifies improvement opportunities."""

    async def analyze(self) -> list[ImprovementOpportunity]:
        opportunities = []

        # 1. Check reasoning bank for failure patterns
        failure_patterns = await self.reasoning_bank.get_failure_patterns(
            min_occurrences=3,
            lookback_hours=24
        )
        for pattern in failure_patterns:
            opportunities.append(ImprovementOpportunity(
                type="routing_improvement",
                description=f"Tasks matching [{pattern.keywords}] fail {pattern.failure_rate:.0%} with {pattern.model}",
                suggested_action=f"Adjust routing heuristics for {pattern.bead_type} tasks",
                priority=self._calculate_priority(pattern),
                evidence=pattern.task_ids,
            ))

        # 2. Check for recurring errors
        errors = await self.error_log.get_recurring(min_count=3, hours=24)
        for error in errors:
            opportunities.append(ImprovementOpportunity(
                type="bug_fix",
                description=f"Recurring error in {error.location}: {error.message}",
                suggested_action=f"Fix {error.exception_type} in {error.file}:{error.line}",
                priority="high" if error.count > 10 else "medium",
                evidence=error.stack_traces[:3],
            ))

        # 3. Check for performance degradation
        slow_components = await self.metrics.get_slow_operations(
            threshold_ms=5000,
            min_occurrences=10
        )
        for op in slow_components:
            opportunities.append(ImprovementOpportunity(
                type="performance",
                description=f"{op.name} averaging {op.avg_ms}ms (p99: {op.p99_ms}ms)",
                suggested_action=f"Optimize {op.function} in {op.module}",
                priority="medium",
                evidence=op.slow_traces,
            ))

        return opportunities
```

### Automatic Bead Creation

```python
async def create_self_improvement_beads(observer: SelfObserver):
    """Periodically check for improvement opportunities and create beads."""

    opportunities = await observer.analyze()

    for opp in opportunities:
        # Check if similar bead already exists
        existing = await bead_repo.find_similar(
            description=opp.description,
            status=["open", "in_progress"]
        )

        if existing:
            # Update existing bead with new evidence
            existing.add_context(f"Additional evidence: {opp.evidence}")
            continue

        # Create new self-improvement bead
        bead = Bead(
            title=f"[Self-Improvement] {opp.suggested_action}",
            description=f"""
## Problem
{opp.description}

## Evidence
{format_evidence(opp.evidence)}

## Suggested Action
{opp.suggested_action}

## Constraints
- Must include tests
- Must not break existing functionality
- Changes to protected files require human approval
""",
            type="self_improvement",
            priority=opp.priority,
            project_id=RINGMASTER_PROJECT_ID,  # Ringmaster's own project
            tags=["self-improvement", opp.type],
        )

        await bead_repo.create(bead)
```

---

## ADR-002: Ringmaster as Its Own Project

**Status:** Proposed
**Context:** For Ringmaster to work on itself, it needs to be registered as a project in its own system.

### Decision

Ringmaster is bootstrapped with itself as **Project #0** - a special project that workers can pick up beads from.

### Bootstrap Sequence

```python
async def bootstrap_ringmaster():
    """Bootstrap Ringmaster with itself as a project."""

    # Check if Ringmaster project exists
    ringmaster_project = await project_repo.get_by_name("ringmaster")

    if not ringmaster_project:
        ringmaster_project = Project(
            id="00000000-0000-0000-0000-000000000000",  # Well-known ID
            name="ringmaster",
            description="Ringmaster orchestration platform (self)",
            repo_url=str(Path(__file__).parent.parent),  # Own repo path
            settings={
                "base_branch": "main",
                "protected_files": [
                    "src/ringmaster/safety.py",
                    "tests/",
                    ".ringmaster/",
                    "migrations/",
                ],
                "require_tests": True,
                "auto_rollback": True,
                "human_approval_for": [
                    "database schema changes",
                    "security-related code",
                    "protected file modifications",
                ],
            },
        )
        await project_repo.create(ringmaster_project)

    return ringmaster_project
```

### Self-Improvement Worker Configuration

```toml
# Workers that can work on Ringmaster itself
[[workers]]
name = "ringmaster-improver"
type = "claude-code"
capabilities = ["python", "fastapi", "self-improvement"]
allowed_projects = ["ringmaster"]  # Only works on Ringmaster
model = "claude-sonnet-4-20250514"  # Use capable model for self-modification

[workers.constraints]
require_tests = true
protected_files = ["src/ringmaster/safety.py", "migrations/"]
```

---

## ADR-003: Self-Improvement Priority Queue

**Status:** Proposed
**Context:** Self-improvement beads compete with user beads. Need policy for prioritization.

### Decision

Self-improvement beads use a **separate priority tier** that runs when workers are idle, unless the improvement is critical.

### Priority Tiers

```python
class PriorityTier(Enum):
    CRITICAL = 0      # Breaking bugs, security issues
    USER_HIGH = 1     # User's high-priority work
    USER_NORMAL = 2   # User's normal work
    SELF_HIGH = 3     # High-impact self-improvements
    USER_LOW = 4      # User's low-priority work
    SELF_NORMAL = 5   # Normal self-improvements
    SELF_LOW = 6      # Nice-to-have improvements

def get_priority_tier(bead: Bead) -> PriorityTier:
    if bead.type == "self_improvement":
        if bead.tags and "critical" in bead.tags:
            return PriorityTier.CRITICAL
        elif bead.priority == "high":
            return PriorityTier.SELF_HIGH
        elif bead.priority == "low":
            return PriorityTier.SELF_LOW
        else:
            return PriorityTier.SELF_NORMAL
    else:
        # User beads
        if bead.priority == "high":
            return PriorityTier.USER_HIGH
        elif bead.priority == "low":
            return PriorityTier.USER_LOW
        else:
            return PriorityTier.USER_NORMAL
```

### Idle-Time Processing

```python
async def pull_bead_with_idle_policy(worker_id: str, worker_type: str) -> Bead | None:
    """Pull bead with idle-time self-improvement policy."""

    # First, try to get user work
    user_bead = await pull_bead(
        worker_id=worker_id,
        worker_type=worker_type,
        exclude_projects=["ringmaster"],
    )

    if user_bead:
        return user_bead

    # No user work - check if we should do self-improvement
    idle_minutes = await get_worker_idle_time(worker_id)

    if idle_minutes >= 5:  # Idle for 5+ minutes
        self_bead = await pull_bead(
            worker_id=worker_id,
            worker_type=worker_type,
            project_id="ringmaster",
        )
        if self_bead:
            logger.info(f"Worker {worker_id} picking up self-improvement: {self_bead.title}")
            return self_bead

    return None
```

### Configuration

```toml
[self_improvement]
enabled = true

# When to work on self-improvement
idle_threshold_minutes = 5  # Start after 5 min idle
max_concurrent_self_beads = 1  # Only 1 self-improvement at a time

# Critical issues bypass idle policy
critical_bypass = true
critical_keywords = ["crash", "security", "data loss", "infinite loop"]
```

---

## ADR-004: Self-Modification Validation Pipeline

**Status:** Proposed
**Context:** Changes to Ringmaster's own code need rigorous validation before hot-reload.

### Decision

Self-modifications go through an **extended validation pipeline** with multiple gates.

### Validation Pipeline

```
Self-Improvement Bead Completed
            │
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GATE 1: Static Analysis                                             │
│  ├─ ruff check (linting)                                            │
│  ├─ mypy (type checking)                                            │
│  └─ bandit (security scanning)                                      │
└───────────────────────────────┬─────────────────────────────────────┘
            │ Pass
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GATE 2: Unit Tests                                                  │
│  ├─ pytest tests/unit/                                              │
│  └─ Coverage check (must not decrease)                              │
└───────────────────────────────┬─────────────────────────────────────┘
            │ Pass
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GATE 3: Integration Tests                                           │
│  ├─ pytest tests/integration/                                       │
│  └─ API contract tests                                              │
└───────────────────────────────┬─────────────────────────────────────┘
            │ Pass
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GATE 4: Staging Deployment (Canary)                                 │
│  ├─ Deploy to staging process                                       │
│  ├─ Run smoke tests against staging                                 │
│  └─ Monitor for 2 minutes                                           │
└───────────────────────────────┬─────────────────────────────────────┘
            │ Pass
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GATE 5: Human Approval (if required)                                │
│  ├─ Protected files modified?                                       │
│  ├─ Database schema changes?                                        │
│  └─ Security-related code?                                          │
└───────────────────────────────┬─────────────────────────────────────┘
            │ Pass/Approved
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GATE 6: Production Hot-Reload                                       │
│  ├─ Restart affected component                                      │
│  ├─ Monitor error rate for 5 minutes                                │
│  └─ Auto-rollback if errors spike                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
class SelfModificationValidator:
    """Validates self-modifications before applying."""

    async def validate(self, bead: Bead, changes: GitDiff) -> ValidationResult:
        results = []

        # Gate 1: Static analysis
        results.append(await self._run_static_analysis())
        if not results[-1].passed:
            return ValidationResult(passed=False, failed_gate="static_analysis", details=results)

        # Gate 2: Unit tests
        results.append(await self._run_unit_tests())
        if not results[-1].passed:
            return ValidationResult(passed=False, failed_gate="unit_tests", details=results)

        # Gate 3: Integration tests
        results.append(await self._run_integration_tests())
        if not results[-1].passed:
            return ValidationResult(passed=False, failed_gate="integration_tests", details=results)

        # Gate 4: Staging deployment
        results.append(await self._deploy_staging_canary(changes))
        if not results[-1].passed:
            return ValidationResult(passed=False, failed_gate="staging", details=results)

        # Gate 5: Human approval check
        if self._requires_human_approval(changes):
            return ValidationResult(
                passed=False,
                failed_gate="human_approval",
                requires_decision=True,
                decision_question=self._format_approval_request(changes),
            )

        return ValidationResult(passed=True, details=results)

    def _requires_human_approval(self, changes: GitDiff) -> bool:
        protected = self.config.get("protected_files", [])
        for file in changes.files:
            if any(file.path.startswith(p) for p in protected):
                return True

        # Check for schema changes
        if any("migrations/" in f.path for f in changes.files):
            return True

        # Check for security-related changes
        security_patterns = ["auth", "password", "secret", "token", "encrypt"]
        for file in changes.files:
            if any(p in file.path.lower() for p in security_patterns):
                return True

        return False
```

---

## ADR-005: Feedback Loop for Improvement Effectiveness

**Status:** Proposed
**Context:** Ringmaster needs to know if self-improvements actually helped.

### Decision

Track **before/after metrics** for each self-improvement to measure effectiveness.

### Metrics Tracked

```python
@dataclass
class ImprovementMetrics:
    """Metrics captured before and after a self-improvement."""

    bead_id: str
    improvement_type: str

    # Captured before improvement
    baseline: dict = field(default_factory=dict)

    # Captured 24h after improvement
    after_24h: dict = field(default_factory=dict)

    # Effectiveness score (-1 to 1, 0 = no change)
    effectiveness: float | None = None

    @staticmethod
    def capture_baseline(improvement_type: str) -> dict:
        """Capture baseline metrics based on improvement type."""

        if improvement_type == "routing_improvement":
            return {
                "failure_rate": get_failure_rate_by_type(),
                "model_cost_per_task": get_avg_cost_per_task(),
                "iterations_per_task": get_avg_iterations(),
            }
        elif improvement_type == "performance":
            return {
                "p50_latency": get_latency_percentile(50),
                "p99_latency": get_latency_percentile(99),
                "error_rate": get_error_rate(),
            }
        elif improvement_type == "bug_fix":
            return {
                "error_count_24h": get_error_count(hours=24),
                "affected_tasks": get_affected_task_count(),
            }
        else:
            return {}

async def record_improvement_outcome(bead: Bead):
    """Record the outcome of a self-improvement after 24h."""

    metrics = await improvement_metrics_repo.get(bead.id)
    if not metrics:
        return

    # Capture current state
    metrics.after_24h = ImprovementMetrics.capture_baseline(bead.tags[1])  # improvement_type in tags

    # Calculate effectiveness
    metrics.effectiveness = calculate_effectiveness(
        metrics.baseline,
        metrics.after_24h,
        metrics.improvement_type
    )

    await improvement_metrics_repo.update(metrics)

    # Log to reasoning bank for future reference
    await reasoning_bank.record_self_improvement(
        bead_id=bead.id,
        improvement_type=metrics.improvement_type,
        effectiveness=metrics.effectiveness,
        details={
            "baseline": metrics.baseline,
            "after": metrics.after_24h,
        }
    )

    # Alert if improvement made things worse
    if metrics.effectiveness < -0.1:
        logger.warning(
            f"Self-improvement {bead.id} appears to have degraded performance: "
            f"effectiveness={metrics.effectiveness}"
        )
        await create_investigation_bead(bead, metrics)
```

### Effectiveness Calculation

```python
def calculate_effectiveness(baseline: dict, after: dict, improvement_type: str) -> float:
    """Calculate improvement effectiveness score (-1 to 1)."""

    if improvement_type == "routing_improvement":
        # Lower failure rate = better
        failure_delta = baseline.get("failure_rate", 0) - after.get("failure_rate", 0)
        # Lower cost = better
        cost_delta = baseline.get("model_cost_per_task", 0) - after.get("model_cost_per_task", 0)

        return (failure_delta * 0.7) + (cost_delta * 0.3)

    elif improvement_type == "performance":
        # Lower latency = better
        latency_improvement = (
            baseline.get("p50_latency", 0) - after.get("p50_latency", 0)
        ) / max(baseline.get("p50_latency", 1), 1)

        return min(max(latency_improvement, -1), 1)

    elif improvement_type == "bug_fix":
        # Fewer errors = better
        error_reduction = (
            baseline.get("error_count_24h", 0) - after.get("error_count_24h", 0)
        ) / max(baseline.get("error_count_24h", 1), 1)

        return min(max(error_reduction, -1), 1)

    return 0.0
```

---

## ADR-006: Incremental Self-Improvement Scope

**Status:** Proposed
**Context:** Large changes are risky. Self-improvements should be small and incremental.

### Decision

Self-improvement beads are **automatically scoped** to small, testable changes.

### Scope Limits

```python
SELF_IMPROVEMENT_LIMITS = {
    "max_files_changed": 5,        # No more than 5 files per improvement
    "max_lines_changed": 200,      # No more than 200 lines per improvement
    "max_new_dependencies": 1,     # At most 1 new dependency
    "forbidden_changes": [
        "delete entire modules",
        "change database schema without migration",
        "modify authentication flow",
        "change API contracts without versioning",
    ],
}

def validate_scope(changes: GitDiff) -> ScopeValidation:
    """Validate that self-improvement is appropriately scoped."""

    violations = []

    if len(changes.files) > SELF_IMPROVEMENT_LIMITS["max_files_changed"]:
        violations.append(
            f"Too many files changed: {len(changes.files)} > {SELF_IMPROVEMENT_LIMITS['max_files_changed']}"
        )

    total_lines = sum(f.additions + f.deletions for f in changes.files)
    if total_lines > SELF_IMPROVEMENT_LIMITS["max_lines_changed"]:
        violations.append(
            f"Too many lines changed: {total_lines} > {SELF_IMPROVEMENT_LIMITS['max_lines_changed']}"
        )

    # Check for forbidden patterns
    for file in changes.files:
        for forbidden in SELF_IMPROVEMENT_LIMITS["forbidden_changes"]:
            if matches_forbidden_pattern(file, forbidden):
                violations.append(f"Forbidden change detected: {forbidden}")

    return ScopeValidation(
        valid=len(violations) == 0,
        violations=violations,
        suggestion="Consider breaking this into smaller improvements" if violations else None
    )
```

### Decomposition Prompt

When a self-improvement is too large, the bead-creator decomposes it:

```markdown
## Self-Improvement Decomposition

The proposed improvement is too large to safely apply:
- Files: {file_count} (max: 5)
- Lines: {line_count} (max: 200)

Break this into smaller improvements:
1. Each improvement should touch 1-3 files
2. Each improvement should be independently testable
3. Improvements can depend on each other

Original goal: {original_description}

Create smaller beads that together achieve this goal.
```

---

## ADR-007: Circuit Breaker for Self-Improvement

**Status:** Proposed
**Context:** Prevent runaway self-modification if something goes wrong.

### Decision

A **circuit breaker** disables self-improvement after consecutive failures.

### Circuit Breaker States

```python
class SelfImprovementCircuitBreaker:
    """Circuit breaker for self-improvement safety."""

    def __init__(self):
        self.state = "closed"  # closed = normal operation
        self.failure_count = 0
        self.last_failure = None
        self.cooldown_until = None

    async def record_outcome(self, bead: Bead, success: bool):
        if success:
            self.failure_count = 0
            if self.state == "half_open":
                self.state = "closed"
                logger.info("Self-improvement circuit breaker closed (recovered)")
        else:
            self.failure_count += 1
            self.last_failure = datetime.now(UTC)

            if self.failure_count >= 3:
                self._trip()

    def _trip(self):
        """Trip the circuit breaker."""
        self.state = "open"
        self.cooldown_until = datetime.now(UTC) + timedelta(hours=1)

        logger.error(
            f"Self-improvement circuit breaker TRIPPED after {self.failure_count} failures. "
            f"Self-improvement disabled until {self.cooldown_until}"
        )

        # Create alert bead for human attention
        asyncio.create_task(self._create_alert_bead())

    async def _create_alert_bead(self):
        bead = Bead(
            title="[ALERT] Self-improvement circuit breaker tripped",
            description=f"""
## Circuit Breaker Tripped

Self-improvement has been automatically disabled after {self.failure_count} consecutive failures.

### Recent Failures
{await self._get_recent_failure_summary()}

### Action Required
1. Review the failed improvements
2. Fix any underlying issues
3. Manually reset the circuit breaker via UI or CLI

### Auto-Reset
The circuit breaker will automatically attempt recovery at {self.cooldown_until}
""",
            type="alert",
            priority="high",
            requires_human=True,
        )
        await bead_repo.create(bead)

    def can_proceed(self) -> bool:
        """Check if self-improvement is allowed."""
        if self.state == "closed":
            return True

        if self.state == "open":
            if datetime.now(UTC) > self.cooldown_until:
                self.state = "half_open"
                logger.info("Self-improvement circuit breaker half-open (attempting recovery)")
                return True
            return False

        if self.state == "half_open":
            return True  # Allow one attempt

        return False
```

### Configuration

```toml
[self_improvement.circuit_breaker]
enabled = true
failure_threshold = 3        # Trip after 3 consecutive failures
cooldown_hours = 1           # Wait 1 hour before retry
auto_recover = true          # Automatically attempt recovery
require_human_reset = false  # Don't require manual reset
```

---

## Summary: Enabling Self-Improvement

| ADR | Purpose | Key Mechanism |
|-----|---------|---------------|
| **ADR-001** | Detect what needs improving | SelfObserver analyzes reasoning bank, errors, metrics |
| **ADR-002** | Work on own codebase | Ringmaster as Project #0 |
| **ADR-003** | Prioritize appropriately | Tier system, idle-time processing |
| **ADR-004** | Validate safely | 6-gate validation pipeline |
| **ADR-005** | Measure effectiveness | Before/after metrics, feedback loop |
| **ADR-006** | Keep changes small | Scope limits, automatic decomposition |
| **ADR-007** | Fail safely | Circuit breaker with auto-recovery |

### Bootstrap Checklist

To enable self-improvement:

1. [ ] Run `ringmaster bootstrap` to create Ringmaster as Project #0
2. [ ] Configure at least one worker with `capabilities = ["self-improvement"]`
3. [ ] Set `[self_improvement] enabled = true` in config
4. [ ] Verify circuit breaker is configured
5. [ ] Run initial observation cycle: `ringmaster self-observe --dry-run`
6. [ ] Review generated improvement beads before enabling auto-creation

### Safety Invariants

These must always hold:

1. **Tests must pass** - No self-modification without passing tests
2. **Scope limits enforced** - No large changes in single bead
3. **Human approval for protected files** - Always
4. **Rollback capability** - Every change must be revertable
5. **Circuit breaker active** - Consecutive failures disable self-improvement
6. **Metrics tracked** - Every improvement measured for effectiveness
