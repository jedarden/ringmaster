# Card State Machine

## Overview

The Card State Machine is the central orchestrator of Ringmaster, managing each task through 16 distinct states covering the complete SDLC lifecycle. It enforces valid transitions, executes guard conditions, and triggers side effects (like starting loops or monitoring builds).

### Heuristic-Based Transitions

**All state transitions are rule-based, not LLM-decided.**

The state machine uses deterministic heuristics for every decision:

| Decision | Implementation | NOT |
|----------|----------------|-----|
| Can transition? | Boolean guard conditions | "Ask LLM if ready" |
| Which state next? | Explicit transition table | "LLM chooses next state" |
| Should retry? | `error_count < max_retries` | "LLM decides retry strategy" |
| Error recovery path? | State-based lookup table | "LLM analyzes error" |

This ensures predictable, auditable behavior. See [09-heuristic-orchestration.md](./09-heuristic-orchestration.md) for detailed rationale.

## State Diagram

```
                                    ┌─────────────────────────────────────────────────────────────────┐
                                    │                        CARD LIFECYCLE                            │
                                    └─────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                                     DEVELOPMENT PHASE                                             │
    └──────────────────────────────────────────────────────────────────────────────────────────────────┘

        ┌─────────┐         ┌─────────────┐         ┌─────────────┐         ┌─────────────────┐
        │  DRAFT  │────────▶│  PLANNING   │────────▶│   CODING    │────────▶│  CODE_REVIEW    │
        └─────────┘         └─────────────┘         └─────────────┘         └─────────────────┘
             │                    │                       │                         │
             │              Plan approved           Code complete              Review approved
             │              Start planning          Start Ralph loop           Create PR
             │                    │                       │                         │
             │                    │                       │                         ▼
             │                    │                       │                  ┌─────────────┐
             │                    │                       │                  │   TESTING   │
             │                    │                       │                  └─────────────┘
             │                    │                       │                         │
             │                    │                       │                   Tests passed
             │                    │                       │                         │
    ┌────────┴────────────────────┴───────────────────────┴─────────────────────────┘
    │
    │   ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    │   │                                      BUILD PHASE                                              │
    │   └──────────────────────────────────────────────────────────────────────────────────────────────┘
    │
    │       ┌───────────────┐         ┌─────────────┐         ┌───────────────────┐
    └──────▶│  BUILD_QUEUE  │────────▶│  BUILDING   │────────▶│  BUILD_SUCCESS    │
            └───────────────┘         └─────────────┘         └───────────────────┘
                                            │                         │
                                            │                         │
                                            ▼                         │
                                     ┌─────────────┐                  │
                                     │ BUILD_FAILED│                  │
                                     └─────────────┘                  │
                                            │                         │
                                            │                         │
    ┌───────────────────────────────────────┴─────────────────────────┘
    │
    │   ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    │   │                                     DEPLOY PHASE                                              │
    │   └──────────────────────────────────────────────────────────────────────────────────────────────┘
    │
    │       ┌───────────────┐         ┌─────────────┐         ┌─────────────────┐
    └──────▶│  DEPLOY_QUEUE │────────▶│  DEPLOYING  │────────▶│   VERIFYING     │
            └───────────────┘         └─────────────┘         └─────────────────┘
                                                                      │
                                            ┌─────────────────────────┤
                                            │                         │
                                            ▼                         ▼
                                     ┌─────────────┐           ┌─────────────┐
                                     │   FAILED    │           │  COMPLETED  │
                                     └─────────────┘           └─────────────┘
                                                                      │
    ┌───────────────────────────────────────────────────────────────────────────────────────┐
    │                                     ERROR & TERMINAL STATES                            │
    └───────────────────────────────────────────────────────────────────────────────────────┘

    Any state can transition to ERROR_FIXING when errors are detected:

    ┌───────────────┐
    │ ERROR_FIXING  │◀──── From any state on error
    └───────────────┘
           │
           │  Fix applied successfully
           │
           ▼
    Return to previous state OR next logical state

    ┌───────────────┐
    │   ARCHIVED    │◀──── Manual archive from any terminal state
    └───────────────┘
```

## State Definitions

### Development Phase States

| State | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `DRAFT` | Initial state for new cards | Card created | User starts planning |
| `PLANNING` | AI generates implementation plan | User approval | Plan approved by user |
| `CODING` | Ralph loop active, generating code | Plan approved | Code complete (loop signals) |
| `CODE_REVIEW` | Human review of generated code | Code complete | Review approved/rejected |
| `TESTING` | Running tests on generated code | Review approved | Tests pass/fail |

### Build Phase States

| State | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `BUILD_QUEUE` | Waiting for build slot | Tests passed | Build starts |
| `BUILDING` | GitHub Actions running | Build started | Build completes |
| `BUILD_SUCCESS` | Build completed successfully | GH Actions success | Move to deploy |
| `BUILD_FAILED` | Build failed | GH Actions failure | Retry or error fixing |

### Deploy Phase States

| State | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `DEPLOY_QUEUE` | Waiting for deploy slot | Build success | Deploy starts |
| `DEPLOYING` | ArgoCD sync in progress | Deploy started | Sync completes |
| `VERIFYING` | Health checks running | Sync success | Verification pass/fail |

### Terminal States

| State | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `COMPLETED` | Successfully deployed and verified | Verification passed | Archive only |
| `FAILED` | Permanently failed (max retries) | Max errors reached | Archive only |
| `ERROR_FIXING` | Automatic error resolution in progress | Error detected | Fix applied |
| `ARCHIVED` | Removed from active view | User action | None (terminal) |

## State Transition Table

```rust
// Comprehensive state transition definitions

pub struct Transition {
    pub from: CardState,
    pub to: CardState,
    pub trigger: Trigger,
    pub guard: Option<Guard>,
    pub action: Option<Action>,
}

pub enum Trigger {
    // User triggers
    StartPlanning,
    ApprovePlan,
    RejectPlan,
    ApproveReview,
    RejectReview,
    Archive,

    // System triggers
    LoopComplete,
    LoopFailed,
    TestsPassed,
    TestsFailed,
    BuildStarted,
    BuildSucceeded,
    BuildFailed,
    DeployStarted,
    DeploySynced,
    DeployFailed,
    VerifyPassed,
    VerifyFailed,
    ErrorDetected,
    FixApplied,
    MaxRetriesExceeded,
}

pub enum Guard {
    HasAcceptanceCriteria,
    HasPlan,
    HasGeneratedCode,
    HasPullRequest,
    TestsExist,
    BuildSucceeded,
    SyncCompleted,
    HealthCheckPassed,
    UnderRetryLimit,
}

pub enum Action {
    CreateGitWorktree,
    StartRalphLoop,
    PauseRalphLoop,
    StopRalphLoop,
    CreatePullRequest,
    TriggerBuild,
    MonitorBuild,
    TriggerDeploy,
    MonitorArgoCD,
    RunHealthChecks,
    CollectErrorContext,
    RestartLoopWithError,
    NotifyUser,
    RecordMetrics,
}
```

## Complete Transition Map

```
┌─────────────────┬─────────────────┬─────────────────────┬────────────────────────┬─────────────────────────┐
│ From State      │ To State        │ Trigger             │ Guard                  │ Action                  │
├─────────────────┼─────────────────┼─────────────────────┼────────────────────────┼─────────────────────────┤
│ DRAFT           │ PLANNING        │ StartPlanning       │ -                      │ -                       │
│ PLANNING        │ CODING          │ ApprovePlan         │ HasAcceptanceCriteria  │ CreateWorktree,         │
│                 │                 │                     │                        │ StartRalphLoop          │
│ PLANNING        │ DRAFT           │ RejectPlan          │ -                      │ -                       │
│ CODING          │ CODE_REVIEW     │ LoopComplete        │ HasGeneratedCode       │ PauseLoop, CreatePR     │
│ CODING          │ ERROR_FIXING    │ ErrorDetected       │ UnderRetryLimit        │ CollectErrorContext     │
│ CODE_REVIEW     │ TESTING         │ ApproveReview       │ HasPullRequest         │ MergePR                 │
│ CODE_REVIEW     │ CODING          │ RejectReview        │ -                      │ RestartLoop             │
│ TESTING         │ BUILD_QUEUE     │ TestsPassed         │ TestsExist             │ QueueBuild              │
│ TESTING         │ ERROR_FIXING    │ TestsFailed         │ UnderRetryLimit        │ CollectErrorContext     │
│ BUILD_QUEUE     │ BUILDING        │ BuildStarted        │ -                      │ MonitorBuild            │
│ BUILDING        │ BUILD_SUCCESS   │ BuildSucceeded      │ -                      │ RecordMetrics           │
│ BUILDING        │ BUILD_FAILED    │ BuildFailed         │ -                      │ CollectErrorContext     │
│ BUILD_SUCCESS   │ DEPLOY_QUEUE    │ (auto)              │ -                      │ QueueDeploy             │
│ BUILD_FAILED    │ ERROR_FIXING    │ ErrorDetected       │ UnderRetryLimit        │ RestartLoopWithError    │
│ BUILD_FAILED    │ FAILED          │ MaxRetriesExceeded  │ !UnderRetryLimit       │ NotifyUser              │
│ DEPLOY_QUEUE    │ DEPLOYING       │ DeployStarted       │ -                      │ MonitorArgoCD           │
│ DEPLOYING       │ VERIFYING       │ DeploySynced        │ SyncCompleted          │ RunHealthChecks         │
│ DEPLOYING       │ ERROR_FIXING    │ DeployFailed        │ UnderRetryLimit        │ CollectErrorContext     │
│ VERIFYING       │ COMPLETED       │ VerifyPassed        │ HealthCheckPassed      │ NotifyUser,             │
│                 │                 │                     │                        │ RecordMetrics           │
│ VERIFYING       │ ERROR_FIXING    │ VerifyFailed        │ UnderRetryLimit        │ CollectErrorContext     │
│ ERROR_FIXING    │ CODING          │ FixApplied          │ (if from dev phase)    │ RestartLoopWithError    │
│ ERROR_FIXING    │ BUILD_QUEUE     │ FixApplied          │ (if from build phase)  │ QueueBuild              │
│ ERROR_FIXING    │ DEPLOY_QUEUE    │ FixApplied          │ (if from deploy phase) │ QueueDeploy             │
│ ERROR_FIXING    │ FAILED          │ MaxRetriesExceeded  │ !UnderRetryLimit       │ NotifyUser              │
│ COMPLETED       │ ARCHIVED        │ Archive             │ -                      │ -                       │
│ FAILED          │ ARCHIVED        │ Archive             │ -                      │ -                       │
└─────────────────┴─────────────────┴─────────────────────┴────────────────────────┴─────────────────────────┘
```

## State Machine Implementation

```rust
// File: crates/core/src/state_machine.rs

use std::collections::HashMap;
use async_trait::async_trait;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CardState {
    Draft,
    Planning,
    Coding,
    CodeReview,
    Testing,
    BuildQueue,
    Building,
    BuildSuccess,
    BuildFailed,
    DeployQueue,
    Deploying,
    Verifying,
    Completed,
    ErrorFixing,
    Archived,
    Failed,
}

impl CardState {
    /// Returns the phase this state belongs to
    pub fn phase(&self) -> Phase {
        match self {
            CardState::Draft | CardState::Planning | CardState::Coding |
            CardState::CodeReview | CardState::Testing => Phase::Development,

            CardState::BuildQueue | CardState::Building |
            CardState::BuildSuccess | CardState::BuildFailed => Phase::Build,

            CardState::DeployQueue | CardState::Deploying |
            CardState::Verifying => Phase::Deploy,

            CardState::Completed | CardState::ErrorFixing |
            CardState::Archived | CardState::Failed => Phase::Terminal,
        }
    }

    /// Returns whether this state allows Ralph loop execution
    pub fn allows_loop(&self) -> bool {
        matches!(self, CardState::Coding | CardState::ErrorFixing)
    }

    /// Returns whether this state is terminal
    pub fn is_terminal(&self) -> bool {
        matches!(self, CardState::Completed | CardState::Archived | CardState::Failed)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Development,
    Build,
    Deploy,
    Terminal,
}

pub struct CardStateMachine {
    transitions: HashMap<(CardState, Trigger), TransitionDef>,
    action_executor: Box<dyn ActionExecutor>,
}

impl CardStateMachine {
    pub fn new(action_executor: Box<dyn ActionExecutor>) -> Self {
        let mut machine = Self {
            transitions: HashMap::new(),
            action_executor,
        };
        machine.register_transitions();
        machine
    }

    fn register_transitions(&mut self) {
        // Development phase
        self.add_transition(CardState::Draft, Trigger::StartPlanning,
            TransitionDef::new(CardState::Planning));

        self.add_transition(CardState::Planning, Trigger::ApprovePlan,
            TransitionDef::new(CardState::Coding)
                .with_guard(Guard::HasAcceptanceCriteria)
                .with_actions(vec![Action::CreateGitWorktree, Action::StartRalphLoop]));

        self.add_transition(CardState::Coding, Trigger::LoopComplete,
            TransitionDef::new(CardState::CodeReview)
                .with_guard(Guard::HasGeneratedCode)
                .with_actions(vec![Action::PauseRalphLoop, Action::CreatePullRequest]));

        // ... additional transitions registered
    }

    pub async fn transition(&self, card: &mut Card, trigger: Trigger) -> Result<CardState, TransitionError> {
        let current = card.state;
        let key = (current, trigger);

        let def = self.transitions.get(&key)
            .ok_or(TransitionError::InvalidTransition { from: current, trigger })?;

        // Check guard
        if let Some(guard) = &def.guard {
            if !self.evaluate_guard(card, guard) {
                return Err(TransitionError::GuardFailed { guard: guard.clone() });
            }
        }

        // Record previous state for error recovery
        card.previous_state = Some(current);
        card.state = def.to;
        card.state_changed_at = Some(Utc::now());

        // Execute actions
        for action in &def.actions {
            self.action_executor.execute(card, action).await?;
        }

        Ok(def.to)
    }

    fn evaluate_guard(&self, card: &Card, guard: &Guard) -> bool {
        match guard {
            Guard::HasAcceptanceCriteria => !card.acceptance_criteria.is_empty(),
            Guard::HasGeneratedCode => card.has_code_changes(),
            Guard::HasPullRequest => card.pull_request_url.is_some(),
            Guard::UnderRetryLimit => card.error_count < card.max_retries,
            // ... other guards
        }
    }
}

#[async_trait]
pub trait ActionExecutor: Send + Sync {
    async fn execute(&self, card: &mut Card, action: &Action) -> Result<(), ActionError>;
}
```

## Error Recovery Flow

When an error is detected at any phase, the state machine follows this recovery flow:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            ERROR RECOVERY FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘

                              Error Detected
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  Check Retry Count           │
                    │  current_errors < max_errors │
                    └──────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                Yes (under limit)           No (limit exceeded)
                    │                             │
                    ▼                             ▼
    ┌───────────────────────────┐    ┌───────────────────────────┐
    │  Transition to            │    │  Transition to FAILED     │
    │  ERROR_FIXING             │    │  (terminal state)         │
    └───────────────────────────┘    └───────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────┐
    │  Collect Error Context    │
    │  • Build logs             │
    │  • Pod logs               │
    │  • ArgoCD errors          │
    │  • Stack traces           │
    └───────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────┐
    │  Store Error in DB        │
    │  • error_type             │
    │  • message                │
    │  • context                │
    │  • source_state           │
    └───────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────┐
    │  Restart Ralph Loop       │
    │  with Error Context       │
    │  (injected via Layer 4)   │
    └───────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────┐
    │  Loop Generates Fix       │
    │  • Analyzes error         │
    │  • Modifies code          │
    │  • Commits changes        │
    └───────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────┐
    │  Transition based on      │
    │  source_state:            │
    │  • Dev phase → CODING     │
    │  • Build phase → BUILD_Q  │
    │  • Deploy phase → DEPLOY_Q│
    └───────────────────────────┘
```

## Integration with Other Components

### Loop Manager Integration

The state machine triggers the Loop Manager at these points:

1. **PLANNING → CODING**: Calls `LoopManager::start_loop(card_id)` with planning context
2. **ERROR_FIXING entry**: Calls `LoopManager::restart_loop(card_id, error_context)`
3. **CODING → CODE_REVIEW**: Calls `LoopManager::pause_loop(card_id)`

### Event Bus Integration

Every state transition emits events:

```rust
pub struct StateChangedEvent {
    pub card_id: Uuid,
    pub from: CardState,
    pub to: CardState,
    pub trigger: Trigger,
    pub timestamp: DateTime<Utc>,
    pub metadata: HashMap<String, Value>,
}

// Broadcast on every transition
event_bus.publish(Event::StateChanged(StateChangedEvent { ... }));
```

### Database Integration

State changes are persisted atomically:

```sql
-- Transition stored in cards table
UPDATE cards
SET state = $1,
    previous_state = $2,
    state_changed_at = NOW(),
    updated_at = NOW()
WHERE id = $3;

-- Transition history (for audit)
INSERT INTO state_transitions (card_id, from_state, to_state, trigger, created_at)
VALUES ($1, $2, $3, $4, NOW());
```

## Configuration

The state machine supports configuration overrides:

```toml
# config.toml

[state_machine]
# Maximum errors before transitioning to FAILED
max_retries = 5

# Timeout for each phase (seconds)
[state_machine.timeouts]
planning = 3600      # 1 hour
coding = 14400       # 4 hours
building = 1800      # 30 minutes
deploying = 600      # 10 minutes
verifying = 300      # 5 minutes

# Auto-transitions
[state_machine.auto]
# Automatically move from BUILD_SUCCESS to DEPLOY_QUEUE
build_success_to_deploy = true

# Automatically archive completed cards after N days
archive_completed_after_days = 30
```
