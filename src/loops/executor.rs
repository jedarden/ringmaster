//! Loop Executor - runs autonomous coding iterations with Claude API
//!
//! This module implements the core execution engine that:
//! 1. Runs coding iterations using the Claude API
//! 2. Persists chat history to the database
//! 3. Handles completion signals and error recovery
//! 4. Creates checkpoints for recovery

use std::sync::Arc;
use std::time::Duration;

use chrono::Utc;
use sqlx::SqlitePool;
use tokio::sync::RwLock;
use tokio::time::sleep;
use uuid::Uuid;

use crate::db::{complete_attempt, create_attempt, get_card, set_card_state};
use crate::domain::{Card, CardState, DiffStats, Project};
use crate::events::{Event, EventBus, LoopCompletionResult};
use crate::integrations::claude::{ClaudeClient, ClaudeError, CompletionResponse, Message};
use crate::prompt::PromptPipeline;

use super::{LoopConfig, LoopManager, LoopState, LoopStatus, StopReason};

/// Extracted commit information from response
#[derive(Debug, Clone)]
pub struct CommitInfo {
    pub sha: String,
    pub diff_stats: Option<DiffStats>,
}

/// Extract commit SHA from Claude's response text
///
/// Looks for common patterns in response where Claude reports making commits:
/// - "git commit" output containing SHA
/// - Commit SHA patterns (40-char hex or 7-char short SHA)
fn extract_commit_sha(response: &str) -> Option<String> {
    use regex::Regex;

    // Pattern for full SHA (40 characters)
    let full_sha_re = Regex::new(r"\b[a-f0-9]{40}\b").ok()?;
    // Pattern for short SHA (7-8 characters) often preceded by commit context
    let short_sha_re = Regex::new(r"(?i)(?:commit|committed|sha)[:\s]+([a-f0-9]{7,8})\b").ok()?;
    // Pattern from git commit output like "[main abc1234] message"
    let git_output_re = Regex::new(r"\[[\w\-/]+\s+([a-f0-9]{7,8})\]").ok()?;

    // Try to find a full SHA first
    if let Some(m) = full_sha_re.find(response) {
        return Some(m.as_str().to_string());
    }

    // Try git output format
    if let Some(caps) = git_output_re.captures(response) {
        if let Some(m) = caps.get(1) {
            return Some(m.as_str().to_string());
        }
    }

    // Try short SHA with commit context
    if let Some(caps) = short_sha_re.captures(response) {
        if let Some(m) = caps.get(1) {
            return Some(m.as_str().to_string());
        }
    }

    None
}

/// Extract diff statistics from Claude's response
///
/// Looks for patterns like:
/// - "X file(s) changed, Y insertion(s), Z deletion(s)"
/// - Git diff stat output
fn extract_diff_stats(response: &str) -> Option<DiffStats> {
    use regex::Regex;

    // Pattern for git diff --stat summary
    let stat_re = Regex::new(
        r"(\d+)\s*files?\s*changed(?:,\s*(\d+)\s*insertions?\(\+\))?(?:,\s*(\d+)\s*deletions?\(-\))?"
    ).ok()?;

    if let Some(caps) = stat_re.captures(response) {
        let files_changed = caps.get(1)?.as_str().parse::<i32>().ok()?;
        let insertions = caps
            .get(2)
            .and_then(|m| m.as_str().parse::<i32>().ok())
            .unwrap_or(0);
        let deletions = caps
            .get(3)
            .and_then(|m| m.as_str().parse::<i32>().ok())
            .unwrap_or(0);

        return Some(DiffStats {
            files_changed,
            insertions,
            deletions,
        });
    }

    None
}

/// Extract all commit information from response
fn extract_commit_info(response: &str) -> Option<CommitInfo> {
    let sha = extract_commit_sha(response)?;
    let diff_stats = extract_diff_stats(response);
    Some(CommitInfo { sha, diff_stats })
}

/// Execution result for a single iteration
#[derive(Debug)]
pub struct IterationResult {
    pub iteration: i32,
    pub response: CompletionResponse,
    pub had_completion_signal: bool,
    pub had_error: bool,
    pub error_message: Option<String>,
}

/// Loop executor that runs autonomous coding loops
pub struct LoopExecutor {
    pool: SqlitePool,
    event_bus: EventBus,
    loop_manager: Arc<RwLock<LoopManager>>,
    claude_client: ClaudeClient,
    prompt_pipeline: PromptPipeline,
}

impl LoopExecutor {
    /// Create a new loop executor
    pub fn new(
        pool: SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
    ) -> Result<Self, ClaudeError> {
        let claude_client = ClaudeClient::new()?;
        let prompt_pipeline = PromptPipeline::new();

        Ok(Self {
            pool,
            event_bus,
            loop_manager,
            claude_client,
            prompt_pipeline,
        })
    }

    /// Create executor with a specific Claude client
    pub fn with_claude_client(
        pool: SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
        claude_client: ClaudeClient,
    ) -> Self {
        Self {
            pool,
            event_bus,
            loop_manager,
            claude_client,
            prompt_pipeline: PromptPipeline::new(),
        }
    }

    /// Start and run a coding loop for a card
    pub async fn run_loop(
        &self,
        card_id: Uuid,
        project: &Project,
        config: LoopConfig,
    ) -> Result<LoopState, ExecutorError> {
        // Start the loop
        {
            let mut manager = self.loop_manager.write().await;
            manager.start_loop(card_id, config.clone())?;
        }

        // Emit loop started event
        self.emit_loop_event(&card_id, "loop_started", None).await;

        // Load chat history from database
        let mut chat_history = self.load_chat_history(&card_id).await?;

        // Run iterations until stopped
        loop {
            // Check if loop should continue
            let should_stop = {
                let mut manager = self.loop_manager.write().await;
                let state = manager
                    .get_loop_state_mut(&card_id)
                    .ok_or_else(|| ExecutorError::LoopNotFound(card_id))?;

                // Check for pause/stop
                if state.status == LoopStatus::Paused {
                    // Wait and check again
                    drop(manager);
                    sleep(Duration::from_millis(500)).await;
                    continue;
                }

                if state.status == LoopStatus::Stopped {
                    Some(StopReason::UserStopped)
                } else {
                    state.should_stop()
                }
            };

            if let Some(reason) = should_stop {
                return self.complete_loop(&card_id, reason).await;
            }

            // Get current card state
            let card = get_card(&self.pool, &card_id.to_string())
                .await?
                .ok_or_else(|| ExecutorError::CardNotFound(card_id))?;

            // Run one iteration
            let result = self
                .run_iteration(&card, project, &mut chat_history)
                .await;

            match result {
                Ok(iter_result) => {
                    // Record successful iteration
                    let cost = iter_result.response.cost_usd(self.claude_client.model());
                    {
                        let mut manager = self.loop_manager.write().await;
                        manager.record_iteration(
                            &card_id,
                            (iter_result.response.input_tokens + iter_result.response.output_tokens)
                                as i64,
                            cost,
                            iter_result.had_error,
                        )?;
                    }

                    // Check for completion signal
                    if iter_result.had_completion_signal {
                        return self.complete_loop(&card_id, StopReason::CompletionSignal).await;
                    }

                    // Emit progress event
                    self.emit_loop_event(&card_id, "iteration_completed", Some(&iter_result))
                        .await;

                    // Check for checkpoint
                    let should_checkpoint = {
                        let manager = self.loop_manager.read().await;
                        manager
                            .get_loop_state(&card_id)
                            .map(|s| s.should_checkpoint())
                            .unwrap_or(false)
                    };

                    if should_checkpoint {
                        self.create_checkpoint(&card_id).await?;
                    }
                }
                Err(e) => {
                    // Record failed iteration
                    {
                        let mut manager = self.loop_manager.write().await;
                        manager.record_iteration(&card_id, 0, 0.0, true)?;
                    }

                    // Check if we should stop due to errors
                    let should_stop = {
                        let manager = self.loop_manager.read().await;
                        manager
                            .get_loop_state(&card_id)
                            .and_then(|s| s.should_stop())
                    };

                    if let Some(reason) = should_stop {
                        return self.complete_loop(&card_id, reason).await;
                    }

                    // Log error and continue
                    tracing::warn!("Iteration error for card {}: {}", card_id, e);
                    self.record_error(&card_id, &e.to_string()).await?;
                }
            }

            // Cooldown between iterations
            let cooldown = {
                let manager = self.loop_manager.read().await;
                manager
                    .get_loop_state(&card_id)
                    .map(|s| s.config.cooldown_seconds)
                    .unwrap_or(3)
            };
            sleep(Duration::from_secs(cooldown)).await;
        }
    }

    /// Run a single iteration
    async fn run_iteration(
        &self,
        card: &Card,
        project: &Project,
        chat_history: &mut Vec<Message>,
    ) -> Result<IterationResult, ExecutorError> {
        // Get current iteration number
        let iteration = {
            let manager = self.loop_manager.read().await;
            manager
                .get_loop_state(&card.id)
                .map(|s| s.iteration)
                .unwrap_or(0)
        };

        // Create attempt record
        let attempt = create_attempt(
            &self.pool,
            &card.id.to_string(),
            iteration + 1,
            self.claude_client.model(),
        )
        .await?;

        // Assemble prompt
        let assembled = self.prompt_pipeline.assemble(card, project);

        // Build messages for API
        let mut messages = chat_history.clone();

        // If this is the first message or chat is empty, add the initial user prompt
        if messages.is_empty() || messages.last().map(|m| m.role.clone()) != Some(crate::integrations::claude::Role::User) {
            messages.push(Message::user(&assembled.user_prompt));
        }

        // Call Claude API
        let response = self
            .claude_client
            .complete(Some(&assembled.system_prompt), &messages)
            .await?;

        // Check for completion signal
        let config = {
            let manager = self.loop_manager.read().await;
            manager
                .get_loop_state(&card.id)
                .map(|s| s.config.clone())
                .unwrap_or_default()
        };
        let had_completion_signal = response.has_completion_signal(&config.completion_signal);

        // Update chat history
        chat_history.push(Message::user(&assembled.user_prompt));
        chat_history.push(Message::assistant(&response.content));

        // Persist chat history
        self.save_chat_message(&card.id, "user", &assembled.user_prompt)
            .await?;
        self.save_chat_message(&card.id, "assistant", &response.content)
            .await?;

        // Extract commit info from response
        let commit_info = extract_commit_info(&response.content);
        let commit_sha = commit_info.as_ref().map(|c| c.sha.as_str());
        let diff_stats = commit_info.as_ref().and_then(|c| c.diff_stats.as_ref());

        // Complete the attempt record
        complete_attempt(
            &self.pool,
            &attempt.id.to_string(),
            &response.content,
            (response.input_tokens + response.output_tokens) as i32,
            response.cost_usd(self.claude_client.model()),
            commit_sha,
            diff_stats,
        )
        .await?;

        // Update card iteration count
        self.update_card_iteration(&card.id, iteration + 1).await?;

        Ok(IterationResult {
            iteration: iteration + 1,
            response,
            had_completion_signal,
            had_error: false,
            error_message: None,
        })
    }

    /// Complete the loop with a stop reason
    async fn complete_loop(
        &self,
        card_id: &Uuid,
        reason: StopReason,
    ) -> Result<LoopState, ExecutorError> {
        let state = {
            let mut manager = self.loop_manager.write().await;
            manager.complete_loop(card_id, reason.clone())?
        };

        // Update card state based on reason
        let new_state = match reason {
            StopReason::CompletionSignal => CardState::CodeReview,
            StopReason::UserStopped => CardState::Draft,
            StopReason::CircuitBreaker | StopReason::Error(_) => CardState::ErrorFixing,
            _ => CardState::Draft,
        };

        set_card_state(&self.pool, &card_id.to_string(), new_state).await?;

        // Emit completion event
        self.emit_loop_event(card_id, "loop_completed", None).await;

        // Remove from active loops
        {
            let mut manager = self.loop_manager.write().await;
            manager.remove_loop(card_id);
        }

        Ok(state)
    }

    /// Create a checkpoint (git commit + snapshot)
    async fn create_checkpoint(&self, card_id: &Uuid) -> Result<(), ExecutorError> {
        let iteration = {
            let manager = self.loop_manager.read().await;
            manager
                .get_loop_state(card_id)
                .map(|s| s.iteration)
                .unwrap_or(0)
        };

        // Save loop snapshot to database
        let snapshot_id = Uuid::new_v4().to_string();
        sqlx::query(
            r#"
            INSERT INTO loop_snapshots (id, card_id, iteration, state)
            VALUES (?, ?, ?, 'checkpoint')
            "#,
        )
        .bind(&snapshot_id)
        .bind(card_id.to_string())
        .bind(iteration)
        .execute(&self.pool)
        .await?;

        // Record checkpoint in manager
        {
            let mut manager = self.loop_manager.write().await;
            manager.record_checkpoint(card_id)?;
        }

        tracing::info!("Created checkpoint for card {} at iteration {}", card_id, iteration);
        Ok(())
    }

    /// Load chat history from database
    async fn load_chat_history(&self, card_id: &Uuid) -> Result<Vec<Message>, ExecutorError> {
        let rows = sqlx::query_as::<_, ChatMessageRow>(
            "SELECT role, content FROM chat_messages WHERE card_id = ? ORDER BY created_at ASC",
        )
        .bind(card_id.to_string())
        .fetch_all(&self.pool)
        .await;

        match rows {
            Ok(messages) => Ok(messages
                .into_iter()
                .map(|row| {
                    if row.role == "user" {
                        Message::user(row.content)
                    } else {
                        Message::assistant(row.content)
                    }
                })
                .collect()),
            Err(sqlx::Error::RowNotFound) => Ok(Vec::new()),
            Err(_) => {
                // Table might not exist yet, return empty history
                Ok(Vec::new())
            }
        }
    }

    /// Save a chat message to database
    async fn save_chat_message(
        &self,
        card_id: &Uuid,
        role: &str,
        content: &str,
    ) -> Result<(), ExecutorError> {
        let id = Uuid::new_v4().to_string();

        // Try to insert, ignore if table doesn't exist
        let result = sqlx::query(
            r#"
            INSERT INTO chat_messages (id, card_id, role, content)
            VALUES (?, ?, ?, ?)
            "#,
        )
        .bind(&id)
        .bind(card_id.to_string())
        .bind(role)
        .bind(content)
        .execute(&self.pool)
        .await;

        if let Err(e) = result {
            tracing::warn!("Failed to save chat message: {}", e);
        }

        Ok(())
    }

    /// Update card iteration count
    async fn update_card_iteration(
        &self,
        card_id: &Uuid,
        iteration: i32,
    ) -> Result<(), ExecutorError> {
        sqlx::query(
            r#"
            UPDATE cards
            SET loop_iteration = ?,
                updated_at = datetime('now')
            WHERE id = ?
            "#,
        )
        .bind(iteration)
        .bind(card_id.to_string())
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    /// Record an error
    async fn record_error(&self, card_id: &Uuid, message: &str) -> Result<(), ExecutorError> {
        let id = Uuid::new_v4().to_string();

        sqlx::query(
            r#"
            INSERT INTO errors (id, card_id, error_type, message, category, severity)
            VALUES (?, ?, 'loop_error', ?, 'runtime', 'error')
            "#,
        )
        .bind(&id)
        .bind(card_id.to_string())
        .bind(message)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    /// Emit a loop event
    async fn emit_loop_event(
        &self,
        card_id: &Uuid,
        event_type: &str,
        result: Option<&IterationResult>,
    ) {
        let state = {
            let manager = self.loop_manager.read().await;
            manager.get_loop_state(card_id).cloned()
        };

        if let Some(state) = state {
            let event = match event_type {
                "loop_started" => Event::LoopStarted {
                    card_id: *card_id,
                    timestamp: Utc::now(),
                },
                "loop_completed" => {
                    let completion_result = match state.stop_reason {
                        Some(StopReason::CompletionSignal) => LoopCompletionResult::CompletionSignal,
                        Some(StopReason::MaxIterations) => LoopCompletionResult::MaxIterations,
                        Some(StopReason::CostLimit) => LoopCompletionResult::CostLimit,
                        Some(StopReason::TimeLimit) => LoopCompletionResult::TimeLimit,
                        Some(StopReason::UserStopped) => LoopCompletionResult::UserStopped,
                        Some(StopReason::CircuitBreaker) => LoopCompletionResult::CircuitBreaker,
                        Some(StopReason::Error(_)) => LoopCompletionResult::Error,
                        None => LoopCompletionResult::UserStopped,
                    };
                    Event::LoopCompleted {
                        card_id: *card_id,
                        result: completion_result,
                        total_iterations: state.iteration,
                        total_cost_usd: state.total_cost_usd,
                        total_tokens: state.total_tokens,
                        timestamp: Utc::now(),
                    }
                }
                "loop_paused" => Event::LoopPaused {
                    card_id: *card_id,
                    iteration: state.iteration,
                    timestamp: Utc::now(),
                },
                _ => {
                    if let Some(r) = result {
                        Event::LoopIteration {
                            card_id: *card_id,
                            iteration: state.iteration,
                            tokens_used: (r.response.input_tokens + r.response.output_tokens) as i32,
                            cost_usd: r.response.cost_usd(self.claude_client.model()),
                            timestamp: Utc::now(),
                        }
                    } else {
                        return;
                    }
                }
            };

            self.event_bus.publish(event);
        }
    }

    /// Pause a running loop
    pub async fn pause_loop(&self, card_id: &Uuid) -> Result<LoopState, ExecutorError> {
        let mut manager = self.loop_manager.write().await;
        let state = manager.pause_loop(card_id)?;
        self.emit_loop_event(card_id, "loop_paused", None).await;
        Ok(state)
    }

    /// Resume a paused loop
    pub async fn resume_loop(&self, card_id: &Uuid) -> Result<LoopState, ExecutorError> {
        let mut manager = self.loop_manager.write().await;
        let state = manager.resume_loop(card_id)?;
        self.emit_loop_event(card_id, "loop_resumed", None).await;
        Ok(state)
    }

    /// Stop a running loop
    pub async fn stop_loop(&self, card_id: &Uuid) -> Result<LoopState, ExecutorError> {
        let mut manager = self.loop_manager.write().await;
        let state = manager.stop_loop(card_id)?;
        self.emit_loop_event(card_id, "loop_stopped", None).await;
        Ok(state)
    }
}

/// Chat message row from database
#[derive(Debug, sqlx::FromRow)]
struct ChatMessageRow {
    role: String,
    content: String,
}

/// Executor errors
#[derive(Debug, thiserror::Error)]
pub enum ExecutorError {
    #[error("Loop not found for card: {0}")]
    LoopNotFound(Uuid),

    #[error("Card not found: {0}")]
    CardNotFound(Uuid),

    #[error("Claude API error: {0}")]
    ClaudeError(#[from] ClaudeError),

    #[error("Database error: {0}")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Loop manager error: {0}")]
    LoopManagerError(String),
}

impl From<String> for ExecutorError {
    fn from(s: String) -> Self {
        ExecutorError::LoopManagerError(s)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_iteration_result() {
        // Basic test that types compile correctly
        let result = IterationResult {
            iteration: 1,
            response: CompletionResponse {
                content: "test".to_string(),
                raw_content: vec!["test".to_string()],
                input_tokens: 100,
                output_tokens: 50,
                stop_reason: crate::integrations::claude::StopReason::EndTurn,
                id: "test".to_string(),
                model: "test".to_string(),
            },
            had_completion_signal: false,
            had_error: false,
            error_message: None,
        };

        assert_eq!(result.iteration, 1);
        assert!(!result.had_completion_signal);
    }
}
