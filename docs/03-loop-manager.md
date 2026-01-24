# Ralph-Wiggum Loop Manager

## Overview

The Loop Manager implements the "Ralph-Wiggum" autonomous coding pattern: an iterative loop that repeatedly executes LLM prompts, observes results, and continues until a completion condition is met. Named after the Simpsons character known for persistence, this pattern enables AI agents to self-correct and iterate toward task completion.

### Platform Execution

Coding loops run via **CLI platform execution** (not direct API calls). This allows users to leverage their Claude Max/Pro subscriptions for unlimited usage instead of pay-per-token API billing.

```
┌─────────────────────────────────────────────────────────────────┐
│                    PLATFORM EXECUTOR                              │
├─────────────────────────────────────────────────────────────────┤
│   PlatformExecutor                                               │
│        │                                                         │
│        └── ClaudeCodePlatform                                    │
│              ├── Auto-installs Claude Code CLI if missing        │
│              ├── Spawns: claude --dangerously-skip-permissions   │
│              ├── Streams: --output-format stream-json            │
│              ├── Auth: ~/.claude/ (Max/Pro subscription)         │
│              └── Detects: <ringmaster>COMPLETE</ringmaster>      │
└─────────────────────────────────────────────────────────────────┘
```

See [ADR-003](./adr/003-multi-platform-support.md) for platform abstraction details.

### Heuristic Loop Control

**All loop control decisions are heuristic-based, not LLM-decided.**

The Loop Manager orchestrates LLM calls but never uses LLMs for its own decisions:

| Decision | Heuristic Implementation | NOT |
|----------|-------------------------|-----|
| Should stop? | Configurable thresholds (iterations, cost, time) | "Ask LLM if done" |
| Is task complete? | String pattern match on `<promise>COMPLETE</promise>` | "LLM judges completion" |
| Should pause? | External signal (user click) | "LLM decides to rest" |
| Error recovery? | Consecutive error count vs threshold | "LLM analyzes failures" |
| Create checkpoint? | `iteration % interval == 0` (modulo) | "LLM decides importance" |

The LLM is called **only** to generate code. All meta-decisions about the loop itself use deterministic rules. See [09-heuristic-orchestration.md](./09-heuristic-orchestration.md) for detailed rationale.

## Core Concept

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           RALPH-WIGGUM LOOP PATTERN                                   │
└──────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                              ITERATION CYCLE                                     │
    │                                                                                  │
    │     ┌──────────────┐                                                            │
    │     │   START      │                                                            │
    │     └──────┬───────┘                                                            │
    │            │                                                                     │
    │            ▼                                                                     │
    │     ┌──────────────┐                                                            │
    │     │ Load Context │◀───────────────────────────────────────────────┐           │
    │     │ from DB      │                                                 │           │
    │     └──────┬───────┘                                                 │           │
    │            │                                                         │           │
    │            ▼                                                         │           │
    │     ┌──────────────┐                                                 │           │
    │     │ Process via  │                                                 │           │
    │     │ Prompt       │                                                 │           │
    │     │ Pipeline     │                                                 │           │
    │     └──────┬───────┘                                                 │           │
    │            │                                                         │           │
    │            ▼                                                         │           │
    │     ┌──────────────┐                                                 │           │
    │     │ Call LLM     │                                                 │           │
    │     │ (Claude API) │                                                 │           │
    │     └──────┬───────┘                                                 │           │
    │            │                                                         │           │
    │            ▼                                                         │           │
    │     ┌──────────────┐                                                 │           │
    │     │ Execute      │                                                 │           │
    │     │ Response     │                                                 │           │
    │     │ (code, git)  │                                                 │           │
    │     └──────┬───────┘                                                 │           │
    │            │                                                         │           │
    │            ▼                                                         │           │
    │     ┌──────────────┐                                                 │           │
    │     │ Check        │                                                 │           │
    │     │ Completion   │                                                 │           │
    │     └──────┬───────┘                                                 │           │
    │            │                                                         │           │
    │      ┌─────┴─────┐                                                   │           │
    │      │           │                                                   │           │
    │  Complete?   Continue?                                               │           │
    │      │           │                                                   │           │
    │      ▼           └───────────────────────────────────────────────────┘           │
    │     ┌──────────────┐                                                             │
    │     │ STATE        │                                                             │
    │     │ TRANSITION   │                                                             │
    │     └──────────────┘                                                             │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

## Stop Conditions

The loop terminates when ANY of these conditions are met:

```rust
pub enum StopCondition {
    /// Completion signal detected in LLM response
    CompletionSignal(String),  // e.g., "<promise>COMPLETE</promise>"

    /// Maximum iterations reached
    MaxIterations(u32),  // e.g., 100

    /// Maximum runtime exceeded
    MaxRuntime(Duration),  // e.g., 4 hours

    /// Maximum cost exceeded
    MaxCost(f64),  // e.g., $300.00

    /// Consecutive errors threshold (circuit breaker)
    CircuitBreaker(u32),  // e.g., 5 consecutive errors

    /// External pause/stop signal
    ExternalSignal,

    /// Manual user intervention
    UserStop,
}
```

### Stop Condition Evaluation

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           STOP CONDITION EVALUATION                                   │
└──────────────────────────────────────────────────────────────────────────────────────┘

    After each iteration:

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │  1. Check completion signal in response                                          │
    │     └── Response contains "<promise>COMPLETE</promise>" ?                        │
    │         └── YES: Stop with SUCCESS                                               │
    │                                                                                  │
    │  2. Check iteration count                                                        │
    │     └── iteration >= max_iterations ?                                            │
    │         └── YES: Stop with MAX_ITERATIONS_REACHED                                │
    │                                                                                  │
    │  3. Check runtime                                                                │
    │     └── elapsed_time >= max_runtime ?                                            │
    │         └── YES: Stop with TIMEOUT                                               │
    │                                                                                  │
    │  4. Check cost                                                                   │
    │     └── total_cost >= max_cost ?                                                 │
    │         └── YES: Stop with COST_LIMIT_EXCEEDED                                   │
    │                                                                                  │
    │  5. Check consecutive errors                                                     │
    │     └── consecutive_errors >= circuit_breaker_threshold ?                        │
    │         └── YES: Stop with CIRCUIT_BREAKER_TRIPPED                               │
    │                                                                                  │
    │  6. Check external signals                                                       │
    │     └── pause_requested || stop_requested ?                                      │
    │         └── pause: Enter PAUSED state                                            │
    │         └── stop: Stop with USER_CANCELLED                                       │
    │                                                                                  │
    │  7. None triggered                                                               │
    │     └── Continue to next iteration                                               │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

## Loop State Machine

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              LOOP STATE MACHINE                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘

                                  start_loop()
                                       │
                                       ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                                PENDING                                           │
    │                           (initial state)                                        │
    └─────────────────────────────────┬───────────────────────────────────────────────┘
                                      │
                                      │ loop.run()
                                      ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                                RUNNING                                           │
    │                         (executing iterations)                                   │
    │                                                                                  │
    │  • Increments iteration counter                                                  │
    │  • Processes prompt pipeline                                                     │
    │  • Calls LLM API                                                                 │
    │  • Executes response                                                             │
    │  • Broadcasts events                                                             │
    │  • Checks stop conditions                                                        │
    └───────┬────────────────────┬────────────────────┬────────────────────┬──────────┘
            │                    │                    │                    │
            │ pause()            │ stop()             │ error              │ complete
            ▼                    ▼                    ▼                    ▼
    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
    │    PAUSED     │    │   STOPPED     │    │    FAILED     │    │   COMPLETED   │
    │               │    │               │    │               │    │               │
    │ • Checkpoint  │    │ • Cleanup     │    │ • Error info  │    │ • Final state │
    │ • Preserve    │    │ • Release     │    │ • Retry info  │    │ • Metrics     │
    │   state       │    │   resources   │    │ • Logs        │    │ • Result      │
    └───────┬───────┘    └───────────────┘    └───────────────┘    └───────────────┘
            │
            │ resume()
            ▼
    ┌───────────────────────────────────────────────────────────────────────────┐
    │                            Back to RUNNING                                 │
    └───────────────────────────────────────────────────────────────────────────┘
```

## Implementation

```rust
// File: crates/loops/src/ralph_loop.rs

use std::sync::Arc;
use tokio::sync::{mpsc, watch, Mutex};
use tokio::time::{Duration, Instant};
use uuid::Uuid;

/// Configuration for a Ralph loop
#[derive(Debug, Clone)]
pub struct LoopConfig {
    /// Maximum number of iterations
    pub max_iterations: u32,

    /// Maximum runtime before timeout
    pub max_runtime: Duration,

    /// Maximum cost in USD
    pub max_cost: f64,

    /// Checkpoint interval (create git commit every N iterations)
    pub checkpoint_interval: u32,

    /// Cooldown between iterations (to avoid rate limits)
    pub cooldown: Duration,

    /// Completion signal to detect in LLM response
    pub completion_signal: String,

    /// Number of consecutive errors before circuit breaker trips
    pub circuit_breaker_threshold: u32,
}

impl Default for LoopConfig {
    fn default() -> Self {
        Self {
            max_iterations: 100,
            max_runtime: Duration::from_secs(4 * 60 * 60),  // 4 hours
            max_cost: 300.0,
            checkpoint_interval: 5,
            cooldown: Duration::from_secs(5),
            completion_signal: "<promise>COMPLETE</promise>".to_string(),
            circuit_breaker_threshold: 5,
        }
    }
}

/// Current state of a running loop
#[derive(Debug, Clone)]
pub struct LoopState {
    pub card_id: Uuid,
    pub iteration: u32,
    pub start_time: Instant,
    pub total_cost: f64,
    pub total_tokens: u64,
    pub consecutive_errors: u32,
    pub status: LoopStatus,
    pub last_checkpoint: u32,
    pub progress_notes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum LoopStatus {
    Pending,
    Running,
    Paused,
    Completed(LoopResult),
    Failed(LoopError),
    Stopped,
}

#[derive(Debug, Clone)]
pub enum LoopResult {
    CompletionSignal,
    MaxIterations,
    Timeout,
    CostLimit,
    UserStopped,
}

#[derive(Debug, Clone)]
pub enum LoopError {
    CircuitBreakerTripped,
    LLMError(String),
    ExecutionError(String),
}

/// The main Ralph loop runner
pub struct RalphLoop {
    card_id: Uuid,
    config: LoopConfig,
    state: Arc<Mutex<LoopState>>,

    // Control channels
    pause_tx: watch::Sender<bool>,
    pause_rx: watch::Receiver<bool>,
    stop_tx: watch::Sender<bool>,
    stop_rx: watch::Receiver<bool>,

    // Dependencies
    prompt_pipeline: Arc<PromptPipeline>,
    llm_service: Arc<LLMService>,
    git_service: Arc<GitService>,
    event_bus: Arc<EventBus>,
    db: Arc<DatabasePool>,
}

impl RalphLoop {
    pub fn new(
        card_id: Uuid,
        config: LoopConfig,
        prompt_pipeline: Arc<PromptPipeline>,
        llm_service: Arc<LLMService>,
        git_service: Arc<GitService>,
        event_bus: Arc<EventBus>,
        db: Arc<DatabasePool>,
    ) -> Self {
        let (pause_tx, pause_rx) = watch::channel(false);
        let (stop_tx, stop_rx) = watch::channel(false);

        let state = LoopState {
            card_id,
            iteration: 0,
            start_time: Instant::now(),
            total_cost: 0.0,
            total_tokens: 0,
            consecutive_errors: 0,
            status: LoopStatus::Pending,
            last_checkpoint: 0,
            progress_notes: Vec::new(),
        };

        Self {
            card_id,
            config,
            state: Arc::new(Mutex::new(state)),
            pause_tx,
            pause_rx,
            stop_tx,
            stop_rx,
            prompt_pipeline,
            llm_service,
            git_service,
            event_bus,
            db,
        }
    }

    /// Run the loop until completion or stop condition
    pub async fn run(&self) -> Result<LoopResult, LoopError> {
        {
            let mut state = self.state.lock().await;
            state.status = LoopStatus::Running;
        }

        self.emit_event(LoopEvent::Started).await;

        loop {
            // Check stop signal
            if *self.stop_rx.borrow() {
                let mut state = self.state.lock().await;
                state.status = LoopStatus::Stopped;
                self.emit_event(LoopEvent::Stopped).await;
                return Ok(LoopResult::UserStopped);
            }

            // Handle pause
            while *self.pause_rx.borrow() {
                tokio::time::sleep(Duration::from_millis(100)).await;
            }

            // Check stop conditions before iteration
            if let Some(result) = self.check_stop_conditions().await {
                return result;
            }

            // Execute iteration
            match self.execute_iteration().await {
                Ok(completed) => {
                    if completed {
                        let mut state = self.state.lock().await;
                        state.status = LoopStatus::Completed(LoopResult::CompletionSignal);
                        self.emit_event(LoopEvent::Completed).await;
                        return Ok(LoopResult::CompletionSignal);
                    }

                    // Reset error count on success
                    let mut state = self.state.lock().await;
                    state.consecutive_errors = 0;
                }
                Err(e) => {
                    let mut state = self.state.lock().await;
                    state.consecutive_errors += 1;

                    if state.consecutive_errors >= self.config.circuit_breaker_threshold {
                        state.status = LoopStatus::Failed(LoopError::CircuitBreakerTripped);
                        self.emit_event(LoopEvent::CircuitBreakerTripped).await;
                        return Err(LoopError::CircuitBreakerTripped);
                    }

                    self.emit_event(LoopEvent::Error(e.to_string())).await;
                }
            }

            // Cooldown between iterations
            tokio::time::sleep(self.config.cooldown).await;
        }
    }

    /// Execute a single loop iteration
    async fn execute_iteration(&self) -> Result<bool, Box<dyn std::error::Error>> {
        let mut state = self.state.lock().await;
        state.iteration += 1;
        let iteration = state.iteration;
        drop(state);

        self.emit_event(LoopEvent::IterationStarted(iteration)).await;

        // Load card from database
        let card = self.db.get_card(self.card_id).await?;

        // Process through prompt pipeline
        let processed = self.prompt_pipeline
            .process(self.card_id, &card.task_prompt)
            .await?;

        // Call LLM
        let response = self.llm_service
            .complete(&processed.final_prompt)
            .await?;

        // Update metrics
        {
            let mut state = self.state.lock().await;
            state.total_cost += response.cost;
            state.total_tokens += response.tokens_used as u64;
        }

        // Record attempt in database
        let attempt = self.db.create_attempt(Attempt {
            card_id: self.card_id,
            attempt_number: iteration,
            status: AttemptStatus::Running,
            output: Some(response.content.clone()),
            tokens_used: Some(response.tokens_used),
            cost: Some(response.cost),
            ..Default::default()
        }).await?;

        // Check for completion signal
        if response.content.contains(&self.config.completion_signal) {
            self.emit_event(LoopEvent::CompletionSignalDetected).await;
            self.db.update_attempt_status(attempt.id, AttemptStatus::Completed).await?;
            return Ok(true);
        }

        // Execute response (code changes, git operations)
        self.execute_response(&response.content).await?;

        // Checkpoint if needed
        if iteration % self.config.checkpoint_interval == 0 {
            self.create_checkpoint(iteration).await?;
        }

        self.emit_event(LoopEvent::IterationCompleted(iteration)).await;
        self.db.update_attempt_status(attempt.id, AttemptStatus::Completed).await?;

        Ok(false)
    }

    /// Check if any stop condition is met
    async fn check_stop_conditions(&self) -> Option<Result<LoopResult, LoopError>> {
        let state = self.state.lock().await;

        // Max iterations
        if state.iteration >= self.config.max_iterations {
            return Some(Ok(LoopResult::MaxIterations));
        }

        // Max runtime
        if state.start_time.elapsed() >= self.config.max_runtime {
            return Some(Ok(LoopResult::Timeout));
        }

        // Max cost
        if state.total_cost >= self.config.max_cost {
            return Some(Ok(LoopResult::CostLimit));
        }

        None
    }

    /// Create a git checkpoint
    async fn create_checkpoint(&self, iteration: u32) -> Result<(), Box<dyn std::error::Error>> {
        let commit_sha = self.git_service
            .commit(&format!("[ralph] Checkpoint iteration {}", iteration))
            .await?;

        let mut state = self.state.lock().await;
        state.last_checkpoint = iteration;

        // Store snapshot
        self.db.create_loop_snapshot(LoopSnapshot {
            card_id: self.card_id,
            iteration,
            state: serde_json::to_value(&*state)?,
            checkpoint_commit: Some(commit_sha),
        }).await?;

        self.emit_event(LoopEvent::CheckpointCreated(iteration)).await;

        Ok(())
    }

    /// Execute LLM response (parse and apply code changes)
    async fn execute_response(&self, response: &str) -> Result<(), Box<dyn std::error::Error>> {
        // Parse code blocks from response
        let code_blocks = self.parse_code_blocks(response);

        for block in code_blocks {
            match block.file_path {
                Some(path) => {
                    // Write file
                    self.git_service.write_file(&path, &block.content).await?;
                }
                None => {
                    // Execute command (if allowed)
                    if block.language == "bash" || block.language == "sh" {
                        // Only execute safe commands
                        self.execute_safe_command(&block.content).await?;
                    }
                }
            }
        }

        // Stage changes
        self.git_service.stage_all().await?;

        Ok(())
    }

    /// Pause the loop (preserves state)
    pub async fn pause(&self) {
        self.pause_tx.send(true).ok();
        let mut state = self.state.lock().await;
        state.status = LoopStatus::Paused;
        drop(state);
        self.emit_event(LoopEvent::Paused).await;
    }

    /// Resume a paused loop
    pub async fn resume(&self) {
        self.pause_tx.send(false).ok();
        let mut state = self.state.lock().await;
        state.status = LoopStatus::Running;
        drop(state);
        self.emit_event(LoopEvent::Resumed).await;
    }

    /// Stop the loop
    pub async fn stop(&self) {
        self.stop_tx.send(true).ok();
    }

    /// Get current loop state
    pub async fn get_state(&self) -> LoopState {
        self.state.lock().await.clone()
    }

    /// Emit event to event bus
    async fn emit_event(&self, event: LoopEvent) {
        self.event_bus.publish(Event::Loop {
            card_id: self.card_id,
            event,
        }).await;
    }
}
```

## Loop Manager

The Loop Manager maintains all active loops and provides management APIs:

```rust
// File: crates/loops/src/manager.rs

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

pub struct LoopManager {
    active_loops: Arc<RwLock<HashMap<Uuid, Arc<RalphLoop>>>>,
    max_concurrent_loops: usize,
    default_config: LoopConfig,

    // Dependencies
    prompt_pipeline: Arc<PromptPipeline>,
    llm_service: Arc<LLMService>,
    git_service: Arc<GitService>,
    event_bus: Arc<EventBus>,
    db: Arc<DatabasePool>,
}

impl LoopManager {
    pub fn new(
        max_concurrent_loops: usize,
        prompt_pipeline: Arc<PromptPipeline>,
        llm_service: Arc<LLMService>,
        git_service: Arc<GitService>,
        event_bus: Arc<EventBus>,
        db: Arc<DatabasePool>,
    ) -> Self {
        Self {
            active_loops: Arc::new(RwLock::new(HashMap::new())),
            max_concurrent_loops,
            default_config: LoopConfig::default(),
            prompt_pipeline,
            llm_service,
            git_service,
            event_bus,
            db,
        }
    }

    /// Start a new loop for a card
    pub async fn start_loop(
        &self,
        card_id: Uuid,
        config: Option<LoopConfig>,
    ) -> Result<Arc<RalphLoop>, LoopManagerError> {
        // Check concurrency limit
        let loops = self.active_loops.read().await;
        if loops.len() >= self.max_concurrent_loops {
            return Err(LoopManagerError::ConcurrencyLimitReached);
        }

        // Check if loop already exists for card
        if loops.contains_key(&card_id) {
            return Err(LoopManagerError::LoopAlreadyExists(card_id));
        }
        drop(loops);

        let config = config.unwrap_or_else(|| self.default_config.clone());

        let loop_instance = Arc::new(RalphLoop::new(
            card_id,
            config,
            Arc::clone(&self.prompt_pipeline),
            Arc::clone(&self.llm_service),
            Arc::clone(&self.git_service),
            Arc::clone(&self.event_bus),
            Arc::clone(&self.db),
        ));

        // Store in active loops
        {
            let mut loops = self.active_loops.write().await;
            loops.insert(card_id, Arc::clone(&loop_instance));
        }

        // Spawn loop execution
        let loop_clone = Arc::clone(&loop_instance);
        let manager_loops = Arc::clone(&self.active_loops);
        tokio::spawn(async move {
            let result = loop_clone.run().await;

            // Remove from active loops when done
            let mut loops = manager_loops.write().await;
            loops.remove(&card_id);

            tracing::info!(
                card_id = %card_id,
                result = ?result,
                "Loop completed"
            );
        });

        Ok(loop_instance)
    }

    /// Pause a running loop
    pub async fn pause_loop(&self, card_id: Uuid) -> Result<(), LoopManagerError> {
        let loops = self.active_loops.read().await;
        match loops.get(&card_id) {
            Some(loop_instance) => {
                loop_instance.pause().await;
                Ok(())
            }
            None => Err(LoopManagerError::LoopNotFound(card_id)),
        }
    }

    /// Resume a paused loop
    pub async fn resume_loop(&self, card_id: Uuid) -> Result<(), LoopManagerError> {
        let loops = self.active_loops.read().await;
        match loops.get(&card_id) {
            Some(loop_instance) => {
                loop_instance.resume().await;
                Ok(())
            }
            None => Err(LoopManagerError::LoopNotFound(card_id)),
        }
    }

    /// Stop a running loop
    pub async fn stop_loop(&self, card_id: Uuid) -> Result<(), LoopManagerError> {
        let loops = self.active_loops.read().await;
        match loops.get(&card_id) {
            Some(loop_instance) => {
                loop_instance.stop().await;
                Ok(())
            }
            None => Err(LoopManagerError::LoopNotFound(card_id)),
        }
    }

    /// Get state of a specific loop
    pub async fn get_loop_state(&self, card_id: Uuid) -> Option<LoopState> {
        let loops = self.active_loops.read().await;
        match loops.get(&card_id) {
            Some(loop_instance) => Some(loop_instance.get_state().await),
            None => None,
        }
    }

    /// List all active loops
    pub async fn list_active_loops(&self) -> Vec<Uuid> {
        let loops = self.active_loops.read().await;
        loops.keys().copied().collect()
    }

    /// Get stats for all active loops
    pub async fn get_stats(&self) -> LoopManagerStats {
        let loops = self.active_loops.read().await;
        let mut stats = LoopManagerStats::default();

        for loop_instance in loops.values() {
            let state = loop_instance.get_state().await;
            stats.total_active += 1;
            stats.total_cost += state.total_cost;
            stats.total_iterations += state.iteration as u64;
            stats.total_tokens += state.total_tokens;

            match state.status {
                LoopStatus::Running => stats.running += 1,
                LoopStatus::Paused => stats.paused += 1,
                _ => {}
            }
        }

        stats
    }
}

#[derive(Debug, Default)]
pub struct LoopManagerStats {
    pub total_active: usize,
    pub running: usize,
    pub paused: usize,
    pub total_cost: f64,
    pub total_iterations: u64,
    pub total_tokens: u64,
}
```

## Event System

The loop emits events for real-time monitoring:

```rust
#[derive(Debug, Clone)]
pub enum LoopEvent {
    Started,
    IterationStarted(u32),
    IterationCompleted(u32),
    CheckpointCreated(u32),
    CompletionSignalDetected,
    Paused,
    Resumed,
    Stopped,
    Completed,
    Error(String),
    CircuitBreakerTripped,

    // Metrics events
    TokensUsed { iteration: u32, tokens: u32 },
    CostIncurred { iteration: u32, cost: f64 },
}

// Events broadcast via WebSocket to frontend
impl LoopEvent {
    pub fn to_ws_message(&self, card_id: Uuid) -> WsMessage {
        WsMessage {
            event_type: "loop",
            card_id,
            data: serde_json::to_value(self).unwrap(),
            timestamp: Utc::now(),
        }
    }
}
```

## Configuration

```toml
# config.toml

[loops]
# Maximum concurrent loops across all cards
max_concurrent = 5

# Default configuration for new loops
[loops.defaults]
max_iterations = 100
max_runtime_seconds = 14400  # 4 hours
max_cost_usd = 300.0
checkpoint_interval = 5
cooldown_seconds = 5
circuit_breaker_threshold = 5
completion_signal = "<promise>COMPLETE</promise>"

# LLM configuration
[loops.llm]
model = "claude-opus-4-20250514"
max_tokens = 16000
temperature = 0.7

# Cost estimation
[loops.costs]
# Cost per 1M tokens (input/output)
opus_input_per_million = 15.0
opus_output_per_million = 75.0
sonnet_input_per_million = 3.0
sonnet_output_per_million = 15.0
```

## Metrics and Observability

```sql
-- Loop iterations tracking
CREATE TABLE loop_iterations (
    id UUID PRIMARY KEY,
    card_id UUID REFERENCES cards(id),
    iteration INTEGER NOT NULL,

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,

    -- Cost
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd DECIMAL(10, 4),

    -- Result
    status VARCHAR(50),
    completion_signal_found BOOLEAN DEFAULT FALSE,
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Aggregated metrics queries
-- Total cost per card
SELECT card_id, SUM(cost_usd) as total_cost
FROM loop_iterations
GROUP BY card_id;

-- Average iterations to completion
SELECT AVG(iteration) as avg_iterations
FROM loop_iterations
WHERE completion_signal_found = true;

-- Cost distribution by hour
SELECT DATE_TRUNC('hour', started_at), SUM(cost_usd)
FROM loop_iterations
GROUP BY DATE_TRUNC('hour', started_at);
```

## Error Recovery

When errors occur, the loop tracks them for debugging:

```rust
pub struct LoopErrorContext {
    pub iteration: u32,
    pub error_type: String,
    pub error_message: String,
    pub stack_trace: Option<String>,
    pub llm_response: Option<String>,
    pub retry_count: u32,
}

impl RalphLoop {
    async fn handle_error(&self, error: &dyn std::error::Error) -> ErrorAction {
        let state = self.state.lock().await;

        // Log error
        tracing::error!(
            card_id = %self.card_id,
            iteration = state.iteration,
            error = %error,
            consecutive_errors = state.consecutive_errors,
            "Loop iteration error"
        );

        // Store error in database
        self.db.create_error(Error {
            card_id: self.card_id,
            error_type: error.type_name(),
            message: error.to_string(),
            context: Some(serde_json::json!({
                "iteration": state.iteration,
                "consecutive_errors": state.consecutive_errors,
            })),
            ..Default::default()
        }).await.ok();

        // Determine action
        if state.consecutive_errors >= self.config.circuit_breaker_threshold {
            ErrorAction::TripCircuitBreaker
        } else {
            ErrorAction::RetryWithBackoff(
                Duration::from_secs(2u64.pow(state.consecutive_errors))
            )
        }
    }
}
```
