//! Platform-based Loop Executor - runs autonomous coding sessions using CLI platforms
//!
//! This module implements a CLI-based execution engine that:
//! 1. Runs coding sessions using CLI platforms (Claude Code, Aider, etc.)
//! 2. Leverages subscription-based billing (Claude Max/Pro) instead of API tokens
//! 3. Monitors session progress via JSON stream output
//! 4. Handles completion signals and session lifecycle

use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use chrono::Utc;
use sqlx::SqlitePool;
use tokio::sync::RwLock;
use tokio::time::sleep;
use uuid::Uuid;

use crate::config::{load_config, Subscription};
use crate::db::{get_card, set_card_state};
use crate::domain::{CardState, Project};
use crate::events::{Event, EventBus, LoopCompletionResult};
use crate::platforms::{
    CodingPlatform, ClaudeCodePlatform, PlatformError, PlatformRegistry,
    SessionConfig, SessionHandle, SessionResult, SessionEndReason,
};
use crate::prompt::PromptPipeline;

use super::checkpoint::{
    delete_checkpoints, get_latest_checkpoint, has_resumable_checkpoint,
    save_checkpoint, LoopCheckpoint,
};
use super::{LoopConfig, LoopManager, LoopState, LoopStatus, StopReason};

/// Platform-based loop executor that uses CLI tools instead of direct API calls
pub struct PlatformExecutor {
    pool: SqlitePool,
    event_bus: EventBus,
    loop_manager: Arc<RwLock<LoopManager>>,
    platform_registry: Arc<RwLock<PlatformRegistry>>,
    prompt_pipeline: PromptPipeline,
    subscriptions: Vec<Subscription>,
}

impl PlatformExecutor {
    /// Create a new platform executor with default Claude Code platform
    pub fn new(
        pool: SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
    ) -> Self {
        let mut registry = PlatformRegistry::new();

        // Register Claude Code platform by default
        let claude_code = ClaudeCodePlatform::new();
        registry.register(Box::new(claude_code));

        // Load subscriptions from config
        let config = load_config();
        let subscriptions = if config.subscriptions.is_empty() {
            // Create default subscription if none configured
            vec![Subscription::default()]
        } else {
            config.subscriptions
        };

        Self {
            pool,
            event_bus,
            loop_manager,
            platform_registry: Arc::new(RwLock::new(registry)),
            prompt_pipeline: PromptPipeline::new(),
            subscriptions,
        }
    }

    /// Create executor with custom platform registry
    pub fn with_registry(
        pool: SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
        registry: PlatformRegistry,
        subscriptions: Vec<Subscription>,
    ) -> Self {
        Self {
            pool,
            event_bus,
            loop_manager,
            platform_registry: Arc::new(RwLock::new(registry)),
            prompt_pipeline: PromptPipeline::new(),
            subscriptions,
        }
    }

    /// Select the best subscription for a task
    fn select_subscription(&self, preferred: Option<&str>) -> Option<&Subscription> {
        // If a specific subscription is requested, try to find it
        if let Some(name) = preferred {
            if let Some(sub) = self.subscriptions.iter().find(|s| s.name == name && s.enabled) {
                return Some(sub);
            }
        }

        // Otherwise, select by priority (lower = higher priority)
        self.subscriptions
            .iter()
            .filter(|s| s.enabled)
            .min_by_key(|s| s.priority)
    }

    /// Start and run a coding loop for a card using CLI platform
    pub async fn run_loop(
        &self,
        card_id: Uuid,
        project: &Project,
        config: LoopConfig,
        subscription_name: Option<&str>,
    ) -> Result<LoopState, PlatformExecutorError> {
        // Select subscription
        let subscription = self.select_subscription(subscription_name)
            .ok_or_else(|| PlatformExecutorError::NoSubscriptionAvailable)?;

        // Get the platform
        let registry = self.platform_registry.read().await;
        let platform = registry.get(&subscription.platform)
            .ok_or_else(|| PlatformExecutorError::PlatformNotFound(subscription.platform.clone()))?;

        // Get card and validate worktree
        let card = get_card(&self.pool, &card_id.to_string())
            .await?
            .ok_or_else(|| PlatformExecutorError::CardNotFound(card_id))?;

        let worktree_path = card.worktree_path
            .as_ref()
            .ok_or_else(|| PlatformExecutorError::NoWorktreePath(card_id))?;

        // Start the loop in manager
        {
            let mut manager = self.loop_manager.write().await;
            manager.start_loop(card_id, config.clone())?;
        }

        // Emit loop started event
        self.emit_loop_event(&card_id, "loop_started", None).await;

        // Build the prompt
        let assembled = self.prompt_pipeline.assemble(&card, project);

        // Create session config
        let mut env_vars = std::collections::HashMap::new();
        if let Some(config_dir) = &subscription.config_dir {
            env_vars.insert(
                "CLAUDE_CONFIG_DIR".to_string(),
                config_dir.to_string_lossy().to_string(),
            );
        }

        let session_config = SessionConfig {
            model: subscription.model.clone(),
            max_turns: Some(config.max_iterations),
            timeout_seconds: Some(config.max_runtime_seconds),
            completion_signal: config.completion_signal.clone(),
            env_vars,
            ..Default::default()
        };

        // Combine system prompt and user prompt for CLI
        let full_prompt = format!(
            "{}\n\n---\n\n{}",
            assembled.system_prompt,
            assembled.user_prompt
        );

        // Start the session
        let handle = platform.start_session(
            Path::new(worktree_path),
            &full_prompt,
            &session_config,
        ).await?;

        // Monitor session until completion
        let result = self.monitor_session(&card_id, &handle, platform, &config).await;

        // Get final state (used for logging if needed)
        let _final_state = {
            let manager = self.loop_manager.read().await;
            manager.get_loop_state(&card_id).cloned()
        };

        // Clean up
        {
            let mut manager = self.loop_manager.write().await;
            manager.remove_loop(&card_id);
        }

        match result {
            Ok(session_result) => {
                let stop_reason = match session_result.end_reason {
                    SessionEndReason::Completed => StopReason::CompletionSignal,
                    SessionEndReason::MaxTurns => StopReason::MaxIterations,
                    SessionEndReason::Timeout => StopReason::TimeLimit,
                    SessionEndReason::UserStopped => StopReason::UserStopped,
                    SessionEndReason::Error => StopReason::Error("Session error".to_string()),
                    SessionEndReason::ProcessExited => StopReason::Error("Process exited unexpectedly".to_string()),
                };

                self.complete_loop(&card_id, stop_reason).await
            }
            Err(e) => {
                self.complete_loop(&card_id, StopReason::Error(e.to_string())).await
            }
        }
    }

    /// Monitor a running session
    async fn monitor_session(
        &self,
        card_id: &Uuid,
        handle: &SessionHandle,
        platform: &dyn CodingPlatform,
        config: &LoopConfig,
    ) -> Result<SessionResult, PlatformExecutorError> {
        let start_time = std::time::Instant::now();
        let timeout = Duration::from_secs(config.max_runtime_seconds);

        loop {
            // Check timeout
            if start_time.elapsed() > timeout {
                tracing::warn!("Session timeout for card {}", card_id);
                return platform.stop_session(handle).await
                    .map_err(PlatformExecutorError::from);
            }

            // Check if loop was stopped externally
            let should_stop = {
                let manager = self.loop_manager.read().await;
                manager
                    .get_loop_state(card_id)
                    .map(|s| s.status == LoopStatus::Stopped)
                    .unwrap_or(true)
            };

            if should_stop {
                tracing::info!("Loop stopped externally for card {}", card_id);
                return platform.stop_session(handle).await
                    .map_err(PlatformExecutorError::from);
            }

            // Check if session is still running
            if !platform.is_session_running(handle).await {
                // Session ended, get result
                return platform.stop_session(handle).await
                    .map_err(PlatformExecutorError::from);
            }

            // Get session status and update loop state
            if let Ok(status) = platform.get_session_status(handle).await {
                let mut manager = self.loop_manager.write().await;
                if let Some(state) = manager.get_loop_state_mut(card_id) {
                    state.iteration = status.iteration;
                    state.total_tokens = status.tokens_used.unwrap_or(0);
                    state.total_cost_usd = status.cost_usd.unwrap_or(0.0);
                    state.elapsed_seconds = status.runtime_ms / 1000;
                }
            }

            // Emit progress event
            self.emit_progress_event(card_id).await;

            // Wait before next check
            sleep(Duration::from_secs(5)).await;
        }
    }

    /// Complete the loop with a stop reason
    async fn complete_loop(
        &self,
        card_id: &Uuid,
        reason: StopReason,
    ) -> Result<LoopState, PlatformExecutorError> {
        let state = {
            let mut manager = self.loop_manager.write().await;
            if let Ok(s) = manager.complete_loop(card_id, reason.clone()) {
                s
            } else {
                // Loop might have been removed already, create a placeholder
                LoopState::new(*card_id, LoopConfig::default())
            }
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

        Ok(state)
    }

    /// Emit a loop event
    async fn emit_loop_event(
        &self,
        card_id: &Uuid,
        event_type: &str,
        _result: Option<&SessionResult>,
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
                _ => return,
            };

            self.event_bus.publish(event);
        }
    }

    /// Emit progress event
    async fn emit_progress_event(&self, card_id: &Uuid) {
        let state = {
            let manager = self.loop_manager.read().await;
            manager.get_loop_state(card_id).cloned()
        };

        if let Some(state) = state {
            let event = Event::LoopIteration {
                card_id: *card_id,
                iteration: state.iteration,
                tokens_used: state.total_tokens as i32,
                cost_usd: state.total_cost_usd,
                timestamp: Utc::now(),
            };

            self.event_bus.publish(event);
        }
    }

    /// Stop a running loop
    pub async fn stop_loop(&self, card_id: &Uuid) -> Result<LoopState, PlatformExecutorError> {
        let mut manager = self.loop_manager.write().await;
        let state = manager.stop_loop(card_id)?;
        Ok(state)
    }

    /// Pause a running loop
    pub async fn pause_loop(&self, card_id: &Uuid) -> Result<LoopState, PlatformExecutorError> {
        let mut manager = self.loop_manager.write().await;
        let state = manager.pause_loop(card_id)?;
        Ok(state)
    }

    /// Resume a paused loop
    pub async fn resume_loop(&self, card_id: &Uuid) -> Result<LoopState, PlatformExecutorError> {
        let mut manager = self.loop_manager.write().await;
        let state = manager.resume_loop(card_id)?;
        Ok(state)
    }

    /// List available platforms
    pub async fn list_platforms(&self) -> Vec<String> {
        let registry = self.platform_registry.read().await;
        registry.list().iter().map(|s| s.to_string()).collect()
    }

    /// List available subscriptions
    pub fn list_subscriptions(&self) -> &[Subscription] {
        &self.subscriptions
    }

    /// Check if a platform is available
    pub async fn is_platform_available(&self, platform_name: &str) -> bool {
        let registry = self.platform_registry.read().await;
        if let Some(platform) = registry.get(platform_name) {
            platform.is_available().await.unwrap_or(false)
        } else {
            false
        }
    }

    /// Check if a card has a resumable checkpoint
    pub async fn has_checkpoint(&self, card_id: &Uuid) -> Result<bool, PlatformExecutorError> {
        has_resumable_checkpoint(&self.pool, card_id)
            .await
            .map_err(PlatformExecutorError::from)
    }

    /// Get the latest checkpoint for a card
    pub async fn get_checkpoint(
        &self,
        card_id: &Uuid,
    ) -> Result<Option<LoopCheckpoint>, PlatformExecutorError> {
        get_latest_checkpoint(&self.pool, card_id)
            .await
            .map_err(PlatformExecutorError::from)
    }

    /// Clear all checkpoints for a card (call after successful completion)
    pub async fn clear_checkpoints(&self, card_id: &Uuid) -> Result<(), PlatformExecutorError> {
        delete_checkpoints(&self.pool, card_id)
            .await
            .map_err(PlatformExecutorError::from)
    }

    /// Resume a loop from a checkpoint
    pub async fn resume_from_checkpoint(
        &self,
        card_id: Uuid,
        project: &Project,
    ) -> Result<LoopState, PlatformExecutorError> {
        // Get the checkpoint
        let checkpoint = get_latest_checkpoint(&self.pool, &card_id)
            .await?
            .ok_or_else(|| PlatformExecutorError::CheckpointNotFound(card_id))?;

        // Restore the loop state
        let restored_state = checkpoint
            .restore_state()
            .ok_or_else(|| PlatformExecutorError::CheckpointCorrupted(card_id))?;

        tracing::info!(
            "Resuming card {} from checkpoint at iteration {}",
            card_id,
            checkpoint.iteration
        );

        // Select subscription (use the one from checkpoint or default)
        let subscription = self
            .select_subscription(checkpoint.subscription.as_deref())
            .ok_or_else(|| PlatformExecutorError::NoSubscriptionAvailable)?;

        // Get the platform
        let registry = self.platform_registry.read().await;
        let platform = registry.get(&subscription.platform).ok_or_else(|| {
            PlatformExecutorError::PlatformNotFound(subscription.platform.clone())
        })?;

        // Get card and validate worktree
        let card = get_card(&self.pool, &card_id.to_string())
            .await?
            .ok_or_else(|| PlatformExecutorError::CardNotFound(card_id))?;

        let worktree_path = card
            .worktree_path
            .as_ref()
            .ok_or_else(|| PlatformExecutorError::NoWorktreePath(card_id))?;

        // Restore the loop in manager with the checkpointed state
        {
            let mut manager = self.loop_manager.write().await;
            // Start with the restored config, but set the iteration to the checkpoint
            let config = restored_state.config.clone();
            manager.start_loop(card_id, config)?;

            // Update the state to match checkpoint
            if let Some(state) = manager.get_loop_state_mut(&card_id) {
                state.iteration = restored_state.iteration;
                state.total_cost_usd = restored_state.total_cost_usd;
                state.total_tokens = restored_state.total_tokens;
            }
        }

        // Emit loop resumed event
        self.emit_loop_event(&card_id, "loop_resumed", None).await;

        // Build resume prompt with context from checkpoint
        let assembled = self.prompt_pipeline.assemble(&card, project);
        let resume_context = if let Some(summary) = &checkpoint.last_response_summary {
            format!(
                "You were previously working on this task. Here's a summary of your progress:\n{}\n\n\
                 Please continue from where you left off.\n\n---\n\n",
                summary
            )
        } else {
            "Please continue from where you left off.\n\n---\n\n".to_string()
        };

        let full_prompt = format!(
            "{}\n\n---\n\n{}{}",
            assembled.system_prompt, resume_context, assembled.user_prompt
        );

        // Create session config
        let mut env_vars = std::collections::HashMap::new();
        if let Some(config_dir) = &subscription.config_dir {
            env_vars.insert(
                "CLAUDE_CONFIG_DIR".to_string(),
                config_dir.to_string_lossy().to_string(),
            );
        }

        let session_config = SessionConfig {
            model: subscription.model.clone(),
            max_turns: Some(
                restored_state
                    .config
                    .max_iterations
                    .saturating_sub(restored_state.iteration as u32),
            ),
            timeout_seconds: Some(restored_state.config.max_runtime_seconds),
            completion_signal: restored_state.config.completion_signal.clone(),
            env_vars,
            ..Default::default()
        };

        // Start the session
        let handle = platform
            .start_session(Path::new(worktree_path), &full_prompt, &session_config)
            .await?;

        // Monitor session until completion
        let result = self
            .monitor_session_with_checkpoints(
                &card_id,
                &handle,
                platform,
                &restored_state.config,
                &subscription.name,
            )
            .await;

        // Get final state
        let _final_state = {
            let manager = self.loop_manager.read().await;
            manager.get_loop_state(&card_id).cloned()
        };

        // Clean up
        {
            let mut manager = self.loop_manager.write().await;
            manager.remove_loop(&card_id);
        }

        match result {
            Ok(session_result) => {
                let stop_reason = match session_result.end_reason {
                    SessionEndReason::Completed => StopReason::CompletionSignal,
                    SessionEndReason::MaxTurns => StopReason::MaxIterations,
                    SessionEndReason::Timeout => StopReason::TimeLimit,
                    SessionEndReason::UserStopped => StopReason::UserStopped,
                    SessionEndReason::Error => StopReason::Error("Session error".to_string()),
                    SessionEndReason::ProcessExited => {
                        StopReason::Error("Process exited unexpectedly".to_string())
                    }
                };

                // Clear checkpoints on successful completion
                if matches!(stop_reason, StopReason::CompletionSignal) {
                    let _ = self.clear_checkpoints(&card_id).await;
                }

                self.complete_loop(&card_id, stop_reason).await
            }
            Err(e) => self
                .complete_loop(&card_id, StopReason::Error(e.to_string()))
                .await,
        }
    }

    /// Monitor a running session with checkpoint support
    async fn monitor_session_with_checkpoints(
        &self,
        card_id: &Uuid,
        handle: &SessionHandle,
        platform: &dyn CodingPlatform,
        config: &LoopConfig,
        subscription_name: &str,
    ) -> Result<SessionResult, PlatformExecutorError> {
        let start_time = std::time::Instant::now();
        let timeout = Duration::from_secs(config.max_runtime_seconds);
        let mut last_checkpoint_iteration = 0i32;

        loop {
            // Check timeout
            if start_time.elapsed() > timeout {
                tracing::warn!("Session timeout for card {}", card_id);
                // Save checkpoint before stopping
                self.save_checkpoint_if_needed(card_id, subscription_name, config)
                    .await;
                return platform
                    .stop_session(handle)
                    .await
                    .map_err(PlatformExecutorError::from);
            }

            // Check if loop was stopped externally
            let (should_stop, should_checkpoint, current_iteration) = {
                let manager = self.loop_manager.read().await;
                let state = manager.get_loop_state(card_id);
                let stopped = state.map(|s| s.status == LoopStatus::Stopped).unwrap_or(true);
                let checkpoint = state.map(|s| s.should_checkpoint()).unwrap_or(false);
                let iteration = state.map(|s| s.iteration).unwrap_or(0);
                (stopped, checkpoint, iteration)
            };

            if should_stop {
                tracing::info!("Loop stopped externally for card {}", card_id);
                // Save checkpoint before stopping
                self.save_checkpoint_if_needed(card_id, subscription_name, config)
                    .await;
                return platform
                    .stop_session(handle)
                    .await
                    .map_err(PlatformExecutorError::from);
            }

            // Check if session is still running
            if !platform.is_session_running(handle).await {
                // Session ended, get result
                return platform
                    .stop_session(handle)
                    .await
                    .map_err(PlatformExecutorError::from);
            }

            // Get session status and update loop state
            if let Ok(status) = platform.get_session_status(handle).await {
                let mut manager = self.loop_manager.write().await;
                if let Some(state) = manager.get_loop_state_mut(card_id) {
                    state.iteration = status.iteration;
                    state.total_tokens = status.tokens_used.unwrap_or(0);
                    state.total_cost_usd = status.cost_usd.unwrap_or(0.0);
                    state.elapsed_seconds = status.runtime_ms / 1000;
                }
            }

            // Save checkpoint if needed (at checkpoint interval)
            if should_checkpoint && current_iteration > last_checkpoint_iteration {
                self.save_checkpoint_if_needed(card_id, subscription_name, config)
                    .await;
                last_checkpoint_iteration = current_iteration;
            }

            // Emit progress event
            self.emit_progress_event(card_id).await;

            // Wait before next check
            sleep(Duration::from_secs(5)).await;
        }
    }

    /// Save a checkpoint for the current loop state
    async fn save_checkpoint_if_needed(
        &self,
        card_id: &Uuid,
        subscription_name: &str,
        _config: &LoopConfig,
    ) {
        let state = {
            let manager = self.loop_manager.read().await;
            manager.get_loop_state(card_id).cloned()
        };

        if let Some(state) = state {
            let checkpoint = LoopCheckpoint::new(
                *card_id,
                state.iteration,
                "claude-code", // TODO: Get actual platform name
                Some(subscription_name),
                &state,
            );

            if let Err(e) = save_checkpoint(&self.pool, &checkpoint).await {
                tracing::warn!("Failed to save checkpoint for card {}: {}", card_id, e);
            } else {
                tracing::debug!(
                    "Saved checkpoint for card {} at iteration {}",
                    card_id,
                    state.iteration
                );
            }
        }
    }
}

/// Errors for platform executor
#[derive(Debug, thiserror::Error)]
pub enum PlatformExecutorError {
    #[error("No subscription available")]
    NoSubscriptionAvailable,

    #[error("Platform not found: {0}")]
    PlatformNotFound(String),

    #[error("Card not found: {0}")]
    CardNotFound(Uuid),

    #[error("No worktree path for card: {0}")]
    NoWorktreePath(Uuid),

    #[error("Loop not found for card: {0}")]
    LoopNotFound(Uuid),

    #[error("Checkpoint not found for card: {0}")]
    CheckpointNotFound(Uuid),

    #[error("Checkpoint corrupted for card: {0}")]
    CheckpointCorrupted(Uuid),

    #[error("Platform error: {0}")]
    PlatformError(#[from] PlatformError),

    #[error("Database error: {0}")]
    DatabaseError(#[from] sqlx::Error),

    #[error("Loop manager error: {0}")]
    LoopManagerError(String),
}

impl From<String> for PlatformExecutorError {
    fn from(s: String) -> Self {
        PlatformExecutorError::LoopManagerError(s)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_select_subscription_by_priority() {
        let subscriptions = vec![
            Subscription {
                name: "low-priority".to_string(),
                platform: "claude-code".to_string(),
                priority: 100,
                enabled: true,
                ..Default::default()
            },
            Subscription {
                name: "high-priority".to_string(),
                platform: "claude-code".to_string(),
                priority: 10,
                enabled: true,
                ..Default::default()
            },
        ];

        // Create a mock executor to test subscription selection
        // This would require more setup, so we just test the subscription struct
        assert_eq!(subscriptions[0].priority, 100);
        assert_eq!(subscriptions[1].priority, 10);

        // The one with lower priority number should be selected
        let selected = subscriptions
            .iter()
            .filter(|s| s.enabled)
            .min_by_key(|s| s.priority);

        assert!(selected.is_some());
        assert_eq!(selected.unwrap().name, "high-priority");
    }

    #[test]
    fn test_select_subscription_by_name() {
        let subscriptions = vec![
            Subscription {
                name: "personal".to_string(),
                platform: "claude-code".to_string(),
                enabled: true,
                ..Default::default()
            },
            Subscription {
                name: "team".to_string(),
                platform: "claude-code".to_string(),
                enabled: true,
                ..Default::default()
            },
        ];

        // Find by name
        let found = subscriptions.iter().find(|s| s.name == "team" && s.enabled);
        assert!(found.is_some());
        assert_eq!(found.unwrap().name, "team");
    }

    #[test]
    fn test_disabled_subscription_not_selected() {
        let subscriptions = vec![
            Subscription {
                name: "disabled".to_string(),
                platform: "claude-code".to_string(),
                priority: 1, // Highest priority but disabled
                enabled: false,
                ..Default::default()
            },
            Subscription {
                name: "enabled".to_string(),
                platform: "claude-code".to_string(),
                priority: 100,
                enabled: true,
                ..Default::default()
            },
        ];

        // Should select enabled subscription even with higher priority number
        let selected = subscriptions
            .iter()
            .filter(|s| s.enabled)
            .min_by_key(|s| s.priority);

        assert!(selected.is_some());
        assert_eq!(selected.unwrap().name, "enabled");
    }
}
