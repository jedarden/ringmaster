# Heuristic Orchestration Model

## Core Principle

**Ringmaster uses heuristics for orchestration and LLMs for code generation.**

| Layer | Powered By | Purpose |
|-------|------------|---------|
| **Orchestration** | Heuristics | State transitions, loop control, error recovery, build/deploy status |
| **Prompt Assembly** | Heuristics + RLM | Assemble context; RLM summarizes long content |
| **Code Generation** | LLM | Generate code, fix bugs, spawn child research agents |

## Key Term: RLM (Recursive Language Model)

**RLM** is a context summarization technique. When content (like card chat history) is too long, an LLM condenses it while preserving essential information. This ensures the code generation LLM has relevant context to either:
- **Act directly** - generate code, fix bugs, implement features
- **Spawn child agents** - conduct supplemental research if more context is needed

```
Long Chat History (50k tokens)
         │
         ▼
   [RLM Summarization]
         │
         ▼
Condensed History (5k tokens)
         │
         ▼
   Code Gen LLM
         │
    ┌────┴────┐
    ▼         ▼
  Act      Spawn
directly   research
```

## What Uses Heuristics

All orchestration decisions use **deterministic rules**, not LLM reasoning:

### 1. State Machine Transitions

```rust
// HEURISTIC: Rule-based state transition
fn can_transition(&self, card: &Card, trigger: Trigger) -> bool {
    match (card.state, trigger) {
        // Rule: Can only start coding if acceptance criteria exist
        (CardState::Planning, Trigger::ApprovePlan) => {
            !card.acceptance_criteria.is_empty()
        }
        // Rule: Can only move to code review if loop signaled completion
        (CardState::Coding, Trigger::LoopComplete) => {
            card.has_code_changes()
        }
        // Rule: Can retry only if under retry limit
        (CardState::BuildFailed, Trigger::ErrorDetected) => {
            card.error_count < card.max_retries
        }
        // ... all transitions follow explicit rules
    }
}
```

### 2. Loop Stop Conditions

```rust
// HEURISTIC: Configurable thresholds
fn should_stop(&self, state: &LoopState) -> Option<StopReason> {
    // Completion signal detected (string matching)
    if self.last_response.contains("<promise>COMPLETE</promise>") {
        return Some(StopReason::CompletionSignal);
    }
    // Iteration limit (numeric comparison)
    if state.iteration >= self.config.max_iterations {
        return Some(StopReason::MaxIterations);
    }
    // Cost limit (numeric comparison)
    if state.total_cost >= self.config.max_cost {
        return Some(StopReason::CostLimit);
    }
    // Circuit breaker (consecutive error count)
    if state.consecutive_errors >= self.config.circuit_breaker_threshold {
        return Some(StopReason::CircuitBreaker);
    }
    None
}
```

### 3. Error Recovery Routing

```rust
// HEURISTIC: Lookup table based on error source
fn determine_recovery_action(&self, error: &Error, card: &Card) -> RecoveryAction {
    if card.error_count >= card.max_retries {
        return RecoveryAction::FailPermanently;
    }

    // Route based on error source phase
    match error.source_state {
        CardState::Coding | CardState::Testing => CardState::Coding,
        CardState::Building => CardState::BuildQueue,
        CardState::Deploying => CardState::DeployQueue,
        _ => CardState::ErrorFixing,
    }
}
```

### 4. Build/Deploy Status Interpretation

```rust
// HEURISTIC: Pattern matching on status strings
fn evaluate_build_status(&self, workflow: &WorkflowRun) -> BuildDecision {
    match workflow.conclusion.as_str() {
        "success" => BuildDecision::Proceed,
        "failure" => BuildDecision::CollectLogsAndRetry,
        "cancelled" => BuildDecision::Retry,
        _ => BuildDecision::WaitAndPoll,
    }
}

fn evaluate_argocd_health(&self, app: &ArgoCDApp) -> DeployDecision {
    match (app.sync_status.as_str(), app.health_status.as_str()) {
        ("Synced", "Healthy") => DeployDecision::Success,
        ("Synced", "Degraded") => DeployDecision::CollectLogsAndRetry,
        ("OutOfSync", _) => DeployDecision::TriggerSync,
        _ => DeployDecision::WaitAndPoll,
    }
}
```

### 5. Prompt Assembly Order

```rust
// HEURISTIC: Fixed order, token budgets
fn assemble_prompt(&self, card: &Card, context: &Context) -> Prompt {
    let mut prompt = String::new();

    // 1. System prompt (static)
    prompt.push_str(&self.system_prompt);

    // 2. Coding agent prompt (stage-based lookup)
    prompt.push_str(&self.agent_prompts[&card.state]);

    // 3. Chat history (RLM if too long)
    let history = if context.chat_history.tokens > HISTORY_BUDGET {
        self.rlm_summarize(&context.chat_history)  // LLM call
    } else {
        context.chat_history.format()
    };
    prompt.push_str(&history);

    // 4. Other context (prioritized by type)
    prompt.push_str(&self.assemble_other_context(card, context));

    prompt
}
```

## What Uses LLMs

LLMs are used for:

### 1. RLM Summarization (when needed)

When chat history exceeds token budget, an LLM summarizes it:

```rust
async fn rlm_summarize(&self, history: &ChatHistory) -> String {
    let prompt = format!(
        "Summarize this conversation for a coding task. Preserve:\n\
         - Key requirements and decisions\n\
         - Errors encountered and resolutions\n\
         - Current implementation state\n\
         - Remaining work\n\n\
         {}",
        history.format()
    );
    self.llm_service.complete(&prompt).await
}
```

### 2. Code Generation

The main LLM generates code with the assembled context:

```rust
async fn generate_code(&self, prompt: &AssembledPrompt) -> LLMResponse {
    self.llm_service.complete(&prompt.to_string()).await
}
```

### 3. Child Agent Research (LLM-initiated)

The code generation LLM can spawn child agents when it needs more context:

```
Code Gen LLM decides: "I need to understand the existing auth implementation"
         │
         ▼
   Spawns child agent to research auth code
         │
         ▼
   Child returns findings
         │
         ▼
   Code Gen LLM continues with enriched context
```

## Configuration

All heuristic thresholds are configurable:

```toml
# config.toml

[state_machine]
max_retries = 5

[loops]
max_iterations = 100
max_runtime_seconds = 14400
max_cost_usd = 300.0
circuit_breaker_threshold = 5
completion_signal = "<promise>COMPLETE</promise>"

[prompt]
system_prompt_budget = 1000
agent_prompt_budget = 1500
chat_history_budget = 10000
other_context_budget = 15000

[prompt.rlm]
model = "claude-3-haiku"
threshold_percentage = 80

[integrations]
github_poll_interval_seconds = 10
argocd_poll_interval_seconds = 15
```

## Anti-Patterns

```
❌ DON'T: "Ask the LLM what state to transition to"
   ✅ DO:  Use deterministic state transition table

❌ DON'T: "Ask the LLM if the loop should stop"
   ✅ DO:  Check configurable thresholds (iterations, cost, time)

❌ DON'T: "Ask the LLM to interpret build status"
   ✅ DO:  Pattern match on status strings ("success", "failure")

❌ DON'T: "Ask the LLM to decide retry strategy"
   ✅ DO:  Use configurable retry limits
```

## Summary

| Component | Powered By | Method |
|-----------|------------|--------|
| State transitions | Heuristics | Rule-based lookup |
| Loop stop conditions | Heuristics | Numeric thresholds |
| Error recovery | Heuristics | State-based routing |
| Build/deploy status | Heuristics | Pattern matching |
| Prompt assembly order | Heuristics | Fixed order + budgets |
| Long content summarization | RLM (LLM) | When exceeds budget |
| Code generation | LLM | Main task execution |
| Supplemental research | LLM | Child agents when needed |
