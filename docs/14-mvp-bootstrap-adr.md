# MVP Bootstrap ADR

## Overview

This ADR defines the **minimum viable Ringmaster** - the baseline that can then improve itself. Every feature beyond this list should be built BY Ringmaster FOR Ringmaster.

## Principle: Bootstrap Paradox Resolution

Ringmaster needs certain capabilities to improve itself, but those capabilities could theoretically be built by Ringmaster. We resolve this by identifying the **irreducible core** - features that MUST exist before self-improvement is possible.

## ADR-020: MVP Feature Matrix

### Tier 1: Absolute Prerequisites (Must Exist First)

These cannot be built by Ringmaster because they ARE Ringmaster:

| Feature | Status | Location | Notes |
|---------|--------|----------|-------|
| Domain models (Project, Task, Epic) | ✅ Done | `domain/models.py` | Core data structures |
| SQLite persistence | ✅ Done | `db/repositories.py` | State must persist |
| CLI interface | ✅ Done | `cli.py` | Human interaction |
| API server | ✅ Done | `api/app.py` | Web interface |
| Frontend (basic) | ✅ Done | `frontend/` | React UI |
| Worker spawner | ✅ Done | `worker/spawner.py` | Tmux-based |
| Git worktrees | ✅ Done | `git/worktrees.py` | Parallel isolation |
| Hot reload | ✅ Done | `reload/reloader.py` | Self-update capability |

### Tier 2: Self-Improvement Enablers (Bootstrap Priority)

These enable Ringmaster to improve itself. Build these first, manually if needed:

| Feature | Status | ADR | Why Critical |
|---------|--------|-----|--------------|
| **Ringmaster as Project #0** | ❌ Missing | ADR-002 | Ringmaster must be its own project to receive beads |
| **Self-Observer (basic)** | ❌ Missing | ADR-001 | Must detect what needs improvement |
| **Priority Tiers (SELF_*)** | ❌ Missing | ADR-003 | Self-improvement must be lower priority than user work |
| **Validation Pipeline (basic)** | ❌ Missing | ADR-004 | Must validate self-changes before applying |
| **Circuit Breaker** | ❌ Missing | ADR-007 | Must stop if self-improvement breaks things |
| **Audit Log** | ❌ Missing | ADR-018 | Must track what self-improvements were made |

### Tier 3: Operational Essentials (Can Be Self-Built)

Once Tier 2 exists, Ringmaster can build these for itself:

| Feature | ADR | Complexity |
|---------|-----|------------|
| Mailbox pattern (inter-worker) | ADR-008 | Moderate |
| File locking | ADR-009 | Simple |
| Coordinator pattern | ADR-010 | Complex |
| Context persistence | ADR-011 | Moderate |
| Worker scaling | ADR-013 | Moderate |
| Rate limiting | ADR-014 | Simple |
| Notifications | ADR-016 | Simple |
| Context window management | ADR-017 | Moderate |

### Tier 4: Advanced Features (Self-Built Later)

| Feature | ADR | Notes |
|---------|-----|-------|
| MCP server mode | ADR-012 | For Claude Desktop integration |
| Knowledge persistence | ADR-015 | Relevance decay, learning |
| Secrets handling (full) | ADR-019 | Proxy pattern, detection |
| Effectiveness feedback | ADR-005 | Before/after metrics |
| Scope limits | ADR-006 | 5 files, 200 lines |

---

## ADR-021: Ringmaster Bootstrap Sequence

### Phase 1: Manual Bootstrap (Human + Claude Code)

```
1. Register Ringmaster as Project #0
   - repo_url: /home/coder/ringmaster
   - tech_stack: ["python", "fastapi", "react", "sqlite"]
   - auto_create_beads: false (initially)

2. Implement SelfObserver (basic version)
   - Watches: test failures, error logs, TODO comments
   - Outputs: Candidate improvement beads (not auto-queued)

3. Implement Priority Tiers
   - Add SELF_HIGH, SELF_NORMAL, SELF_LOW to Priority enum
   - Update queue manager to respect tiers

4. Implement Validation Pipeline (gates 1-3)
   - Gate 1: Static analysis (ruff, mypy)
   - Gate 2: Unit tests (pytest)
   - Gate 3: Integration tests
   - Gates 4-6 added later by Ringmaster

5. Implement Circuit Breaker
   - 3 consecutive failures → disable self-improvement
   - Manual reset required

6. Implement Audit Log (append-only)
   - All self-improvement attempts logged
   - Success/failure, changes made, metrics
```

### Phase 2: Supervised Self-Improvement

```
1. Enable auto_create_beads for Project #0
2. SelfObserver creates beads automatically
3. Human approves/rejects beads before work starts
4. Workers implement approved beads
5. Human approves/rejects changes before merge
```

### Phase 3: Autonomous Self-Improvement

```
1. SelfObserver creates beads → auto-queued (SELF_* priority)
2. Workers implement without pre-approval
3. Validation pipeline gates changes
4. Only Gate 5 (human approval) blocks merge
5. Eventually: Gate 5 becomes sampling (10% human review)
```

---

## ADR-022: Bootstrap Implementation Spec

### 22.1 Project #0 Registration

```python
# In CLI or first-run script
from ringmaster.db.repositories import ProjectRepository
from ringmaster.domain.models import Project
from uuid import UUID

PROJECT_ZERO_ID = UUID("00000000-0000-0000-0000-000000000000")

def bootstrap_project_zero(repo: ProjectRepository) -> Project:
    """Register Ringmaster as its own project."""

    existing = repo.get(PROJECT_ZERO_ID)
    if existing:
        return existing

    project = Project(
        id=PROJECT_ZERO_ID,
        name="Ringmaster",
        description="Multi-Coding-Agent Orchestration Platform (self)",
        tech_stack=["python", "fastapi", "react", "typescript", "sqlite"],
        repo_url="/home/coder/ringmaster",
        settings={
            "is_self": True,
            "auto_create_beads": False,  # Start supervised
            "self_improvement_enabled": False,
            "validation_gates": ["static", "unit", "integration"],
        },
        pinned=True,
    )

    return repo.create(project)
```

### 22.2 SelfObserver (Minimal)

```python
# src/ringmaster/observer/self_observer.py

from dataclasses import dataclass
from pathlib import Path
import subprocess
import re

@dataclass
class ImprovementCandidate:
    """A potential self-improvement identified by the observer."""
    source: str  # "test_failure", "error_log", "todo_comment", "coverage_gap"
    location: str  # File path or component name
    description: str
    severity: str  # "high", "medium", "low"
    evidence: str  # The actual error/TODO/gap

class SelfObserver:
    """Observes Ringmaster for improvement opportunities.

    Minimal version - no LLM calls, just pattern matching.
    """

    def __init__(self, ringmaster_root: Path):
        self.root = ringmaster_root

    def scan_test_failures(self) -> list[ImprovementCandidate]:
        """Run pytest and extract failures."""
        result = subprocess.run(
            ["pytest", "--tb=short", "-q"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

        candidates = []
        if result.returncode != 0:
            # Parse failure output
            for match in re.finditer(r"FAILED ([\w/]+\.py::\w+)", result.stdout):
                test_path = match.group(1)
                candidates.append(ImprovementCandidate(
                    source="test_failure",
                    location=test_path,
                    description=f"Test {test_path} is failing",
                    severity="high",
                    evidence=result.stdout[-500:],  # Last 500 chars
                ))

        return candidates

    def scan_todo_comments(self) -> list[ImprovementCandidate]:
        """Find TODO/FIXME/HACK comments."""
        candidates = []

        for py_file in self.root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            content = py_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                if match := re.search(r"#\s*(TODO|FIXME|HACK):\s*(.+)", line):
                    tag, desc = match.groups()
                    severity = "high" if tag == "FIXME" else "medium"
                    candidates.append(ImprovementCandidate(
                        source="todo_comment",
                        location=f"{py_file}:{i}",
                        description=desc.strip(),
                        severity=severity,
                        evidence=line.strip(),
                    ))

        return candidates

    def scan_error_logs(self, log_path: Path) -> list[ImprovementCandidate]:
        """Parse error logs for patterns."""
        candidates = []

        if not log_path.exists():
            return candidates

        content = log_path.read_text()

        # Look for repeated errors
        error_counts: dict[str, int] = {}
        for match in re.finditer(r"ERROR.*?:(.*?)(?:\n|$)", content):
            error_msg = match.group(1).strip()[:100]
            error_counts[error_msg] = error_counts.get(error_msg, 0) + 1

        for error_msg, count in error_counts.items():
            if count >= 3:  # Repeated error
                candidates.append(ImprovementCandidate(
                    source="error_log",
                    location="logs",
                    description=f"Repeated error ({count}x): {error_msg}",
                    severity="high" if count >= 10 else "medium",
                    evidence=error_msg,
                ))

        return candidates

    def scan_all(self) -> list[ImprovementCandidate]:
        """Run all scans and return candidates."""
        candidates = []
        candidates.extend(self.scan_test_failures())
        candidates.extend(self.scan_todo_comments())
        # candidates.extend(self.scan_error_logs(...))
        return candidates
```

### 22.3 Priority Tiers Update

```python
# Update domain/enums.py

class Priority(str, Enum):
    """Task priority levels with self-improvement tiers."""

    # User-facing priorities (always higher)
    P0 = "P0"  # Critical/blocker
    P1 = "P1"  # High
    P2 = "P2"  # Normal (default)
    P3 = "P3"  # Low
    P4 = "P4"  # Nice-to-have

    # Self-improvement priorities (always lower than user)
    SELF_HIGH = "SELF_HIGH"      # Important self-fix
    SELF_NORMAL = "SELF_NORMAL"  # Standard self-improvement
    SELF_LOW = "SELF_LOW"        # Optional optimization

    @property
    def numeric_priority(self) -> int:
        """Return numeric priority for sorting (lower = more urgent)."""
        order = {
            "P0": 0, "P1": 10, "P2": 20, "P3": 30, "P4": 40,
            "SELF_HIGH": 100, "SELF_NORMAL": 110, "SELF_LOW": 120,
        }
        return order.get(self.value, 50)
```

### 22.4 Circuit Breaker

```python
# src/ringmaster/observer/circuit_breaker.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json

@dataclass
class CircuitState:
    """State of the self-improvement circuit breaker."""
    consecutive_failures: int = 0
    last_failure_time: datetime | None = None
    is_open: bool = False  # True = disabled
    open_reason: str | None = None

    FAILURE_THRESHOLD = 3
    COOLDOWN_HOURS = 24

class CircuitBreaker:
    """Disables self-improvement after repeated failures."""

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.state = self._load_state()

    def _load_state(self) -> CircuitState:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text())
            return CircuitState(**data)
        return CircuitState()

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps({
            "consecutive_failures": self.state.consecutive_failures,
            "last_failure_time": self.state.last_failure_time.isoformat() if self.state.last_failure_time else None,
            "is_open": self.state.is_open,
            "open_reason": self.state.open_reason,
        }))

    def is_allowed(self) -> bool:
        """Check if self-improvement is allowed."""
        return not self.state.is_open

    def record_success(self) -> None:
        """Record a successful self-improvement."""
        self.state.consecutive_failures = 0
        self._save_state()

    def record_failure(self, reason: str) -> None:
        """Record a failed self-improvement."""
        self.state.consecutive_failures += 1
        self.state.last_failure_time = datetime.utcnow()

        if self.state.consecutive_failures >= CircuitState.FAILURE_THRESHOLD:
            self.state.is_open = True
            self.state.open_reason = f"Circuit opened after {self.state.consecutive_failures} failures. Last: {reason}"

        self._save_state()

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self.state = CircuitState()
        self._save_state()
```

### 22.5 Validation Pipeline (Basic)

```python
# src/ringmaster/observer/validator.py

from dataclasses import dataclass
from pathlib import Path
import subprocess
from enum import Enum

class ValidationGate(str, Enum):
    STATIC = "static"
    UNIT = "unit"
    INTEGRATION = "integration"
    STAGING = "staging"
    HUMAN = "human"
    HOT_RELOAD = "hot_reload"

@dataclass
class ValidationResult:
    gate: ValidationGate
    passed: bool
    output: str
    duration_seconds: float

class ValidationPipeline:
    """Validates self-improvement changes through gates."""

    def __init__(self, ringmaster_root: Path):
        self.root = ringmaster_root

    def run_gate(self, gate: ValidationGate) -> ValidationResult:
        """Run a single validation gate."""
        import time
        start = time.time()

        if gate == ValidationGate.STATIC:
            result = self._run_static()
        elif gate == ValidationGate.UNIT:
            result = self._run_unit()
        elif gate == ValidationGate.INTEGRATION:
            result = self._run_integration()
        else:
            # Gates 4-6 implemented later
            result = (True, "Gate not implemented yet")

        return ValidationResult(
            gate=gate,
            passed=result[0],
            output=result[1],
            duration_seconds=time.time() - start,
        )

    def _run_static(self) -> tuple[bool, str]:
        """Gate 1: Static analysis (ruff, mypy)."""
        ruff = subprocess.run(
            ["ruff", "check", "src/"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

        if ruff.returncode != 0:
            return False, f"Ruff failed:\n{ruff.stdout}"

        mypy = subprocess.run(
            ["mypy", "src/", "--ignore-missing-imports"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

        if mypy.returncode != 0:
            return False, f"Mypy failed:\n{mypy.stdout}"

        return True, "Static analysis passed"

    def _run_unit(self) -> tuple[bool, str]:
        """Gate 2: Unit tests."""
        result = subprocess.run(
            ["pytest", "tests/", "-x", "-q", "--ignore=tests/test_e2e*"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

        return result.returncode == 0, result.stdout + result.stderr

    def _run_integration(self) -> tuple[bool, str]:
        """Gate 3: Integration tests."""
        result = subprocess.run(
            ["pytest", "tests/test_e2e*.py", "-x", "-q"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

        # Integration tests may not exist yet
        if "no tests ran" in result.stdout:
            return True, "No integration tests (skipped)"

        return result.returncode == 0, result.stdout + result.stderr

    def run_all(self, gates: list[ValidationGate]) -> list[ValidationResult]:
        """Run all specified gates, stopping on first failure."""
        results = []
        for gate in gates:
            result = self.run_gate(gate)
            results.append(result)
            if not result.passed:
                break  # Stop on first failure
        return results
```

---

## ADR-023: What Ringmaster Builds First (After Bootstrap)

Once the bootstrap is complete, Ringmaster's first self-improvements should be:

### Priority 1: Robustness
1. **Better error handling** - Catch and log all exceptions cleanly
2. **Retry logic** - Exponential backoff for transient failures
3. **Graceful degradation** - Work without optional dependencies

### Priority 2: Observability
1. **Structured logging** - JSON logs with correlation IDs
2. **Metrics collection** - Task durations, success rates
3. **Health checks** - `/health` endpoint with component status

### Priority 3: Self-Improvement Quality
1. **Effectiveness feedback** (ADR-005) - Track before/after metrics
2. **Scope limits** (ADR-006) - Enforce 5 files, 200 lines
3. **Better validation** - Add gates 4-6

### Priority 4: Coordination
1. **Mailbox pattern** (ADR-008) - Inter-worker communication
2. **File locking** (ADR-009) - Prevent conflicts
3. **Worker scaling** (ADR-013) - Auto-scale based on queue depth

---

## Implementation Order

```
Week 1: Manual Bootstrap
├── Day 1-2: Project #0 registration + CLI command
├── Day 3-4: SelfObserver (basic scans)
└── Day 5: Priority tiers in queue

Week 2: Safety Rails
├── Day 1-2: Circuit breaker
├── Day 3-4: Validation pipeline (gates 1-3)
└── Day 5: Audit log

Week 3: Supervised Self-Improvement
├── Enable auto_create_beads
├── Human approval workflow
└── First self-improvements land

Week 4+: Autonomous
├── Reduce human approval to sampling
├── Ringmaster builds remaining features
└── Flywheel effect begins
```

---

## Success Criteria

Ringmaster is "bootstrapped" when:

1. ✅ Ringmaster is registered as Project #0
2. ✅ SelfObserver creates beads from test failures/TODOs
3. ✅ Beads are queued with SELF_* priority (below user work)
4. ✅ Workers can implement self-improvement beads
5. ✅ Validation pipeline catches breaking changes
6. ✅ Circuit breaker stops runaway failures
7. ✅ Audit log tracks all self-modifications
8. ✅ At least one self-improvement has landed successfully

Once these criteria are met, all future features are built BY Ringmaster.
