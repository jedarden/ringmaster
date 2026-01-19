//! Ralph Loop Manager - manages autonomous coding loops
//!
//! This module provides:
//! - `LoopManager`: Manages loop state and lifecycle
//! - `LoopExecutor`: Executes coding iterations with Claude API
//! - `LoopConfig`: Configuration for loop behavior

pub mod executor;

pub use executor::{ExecutorError, IterationResult, LoopExecutor};

use std::collections::HashMap;
use std::time::Instant;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Loop configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopConfig {
    /// Maximum iterations before stopping
    pub max_iterations: u32,
    /// Maximum runtime in seconds
    pub max_runtime_seconds: u64,
    /// Maximum cost in USD
    pub max_cost_usd: f64,
    /// Create checkpoint every N iterations
    pub checkpoint_interval: u32,
    /// Cooldown between iterations in seconds
    pub cooldown_seconds: u64,
    /// Maximum consecutive errors before stopping
    pub max_consecutive_errors: u32,
    /// Signal that indicates task completion
    pub completion_signal: String,
}

impl Default for LoopConfig {
    fn default() -> Self {
        Self {
            max_iterations: 100,
            max_runtime_seconds: 14400,
            max_cost_usd: 300.0,
            checkpoint_interval: 10,
            cooldown_seconds: 3,
            max_consecutive_errors: 3,
            completion_signal: "<promise>COMPLETE</promise>".to_string(),
        }
    }
}

/// Loop status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LoopStatus {
    Running,
    Paused,
    Completed,
    Stopped,
    Failed,
}

/// Stop reason for a loop
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub enum StopReason {
    CompletionSignal,
    MaxIterations,
    CostLimit,
    TimeLimit,
    UserStopped,
    CircuitBreaker,
    Error(String),
}

/// Current state of a loop
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopState {
    pub card_id: Uuid,
    pub iteration: i32,
    pub status: LoopStatus,
    pub total_cost_usd: f64,
    pub total_tokens: i64,
    pub consecutive_errors: u32,
    pub last_checkpoint: Option<i32>,
    pub start_time: DateTime<Utc>,
    pub elapsed_seconds: u64,
    pub config: LoopConfig,
    pub stop_reason: Option<StopReason>,
}

impl LoopState {
    pub fn new(card_id: Uuid, config: LoopConfig) -> Self {
        Self {
            card_id,
            iteration: 0,
            status: LoopStatus::Running,
            total_cost_usd: 0.0,
            total_tokens: 0,
            consecutive_errors: 0,
            last_checkpoint: None,
            start_time: Utc::now(),
            elapsed_seconds: 0,
            config,
            stop_reason: None,
        }
    }

    /// Calculate the backoff duration for the next iteration
    ///
    /// Uses exponential backoff when there are consecutive errors:
    /// - 0 errors: base cooldown (e.g., 3 seconds)
    /// - 1 error: 2x cooldown (6 seconds)
    /// - 2 errors: 4x cooldown (12 seconds)
    /// - etc., capped at 5 minutes max
    pub fn calculate_backoff_seconds(&self) -> u64 {
        let base_cooldown = self.config.cooldown_seconds;

        if self.consecutive_errors == 0 {
            return base_cooldown;
        }

        // Exponential backoff: base * 2^(errors), with jitter
        let multiplier = 2u64.saturating_pow(self.consecutive_errors);
        let backoff = base_cooldown.saturating_mul(multiplier);

        // Cap at 5 minutes (300 seconds)
        let max_backoff = 300u64;
        backoff.min(max_backoff)
    }

    /// Check if the loop should stop based on current state
    pub fn should_stop(&self) -> Option<StopReason> {
        if self.iteration >= self.config.max_iterations as i32 {
            return Some(StopReason::MaxIterations);
        }
        if self.total_cost_usd >= self.config.max_cost_usd {
            return Some(StopReason::CostLimit);
        }
        if self.elapsed_seconds >= self.config.max_runtime_seconds {
            return Some(StopReason::TimeLimit);
        }
        if self.consecutive_errors >= self.config.max_consecutive_errors {
            return Some(StopReason::CircuitBreaker);
        }
        None
    }

    /// Check if it's time for a checkpoint
    pub fn should_checkpoint(&self) -> bool {
        if self.config.checkpoint_interval == 0 {
            return false;
        }
        self.iteration > 0 && (self.iteration as u32).is_multiple_of(self.config.checkpoint_interval)
    }
}

/// Manages all active loops
pub struct LoopManager {
    /// Active loops by card ID
    loops: HashMap<Uuid, LoopState>,
    /// Start time for elapsed time calculation
    start_times: HashMap<Uuid, Instant>,
}

impl Default for LoopManager {
    fn default() -> Self {
        Self::new()
    }
}

impl LoopManager {
    pub fn new() -> Self {
        Self {
            loops: HashMap::new(),
            start_times: HashMap::new(),
        }
    }

    /// Start a new loop for a card
    pub fn start_loop(&mut self, card_id: Uuid, config: LoopConfig) -> Result<LoopState, String> {
        if self.loops.contains_key(&card_id) {
            return Err(format!("Loop already exists for card {}", card_id));
        }

        let state = LoopState::new(card_id, config);
        self.loops.insert(card_id, state.clone());
        self.start_times.insert(card_id, Instant::now());

        Ok(state)
    }

    /// Get the current state of a loop
    pub fn get_loop_state(&self, card_id: &Uuid) -> Option<&LoopState> {
        self.loops.get(card_id)
    }

    /// Get mutable state of a loop
    pub fn get_loop_state_mut(&mut self, card_id: &Uuid) -> Option<&mut LoopState> {
        // Update elapsed time
        if let Some(start) = self.start_times.get(card_id) {
            if let Some(state) = self.loops.get_mut(card_id) {
                state.elapsed_seconds = start.elapsed().as_secs();
            }
        }
        self.loops.get_mut(card_id)
    }

    /// Pause a loop
    pub fn pause_loop(&mut self, card_id: &Uuid) -> Result<LoopState, String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        if state.status != LoopStatus::Running {
            return Err(format!("Loop is not running (status: {:?})", state.status));
        }

        state.status = LoopStatus::Paused;
        Ok(state.clone())
    }

    /// Resume a paused loop
    pub fn resume_loop(&mut self, card_id: &Uuid) -> Result<LoopState, String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        if state.status != LoopStatus::Paused {
            return Err(format!("Loop is not paused (status: {:?})", state.status));
        }

        state.status = LoopStatus::Running;
        Ok(state.clone())
    }

    /// Stop a loop
    pub fn stop_loop(&mut self, card_id: &Uuid) -> Result<LoopState, String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        state.status = LoopStatus::Stopped;
        state.stop_reason = Some(StopReason::UserStopped);

        Ok(state.clone())
    }

    /// Complete a loop with a reason
    pub fn complete_loop(&mut self, card_id: &Uuid, reason: StopReason) -> Result<LoopState, String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        state.status = LoopStatus::Completed;
        state.stop_reason = Some(reason);

        Ok(state.clone())
    }

    /// Fail a loop with an error
    pub fn fail_loop(&mut self, card_id: &Uuid, error: String) -> Result<LoopState, String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        state.status = LoopStatus::Failed;
        state.stop_reason = Some(StopReason::Error(error));

        Ok(state.clone())
    }

    /// Remove a loop (after completion or failure)
    pub fn remove_loop(&mut self, card_id: &Uuid) -> Option<LoopState> {
        self.start_times.remove(card_id);
        self.loops.remove(card_id)
    }

    /// Record an iteration result
    pub fn record_iteration(
        &mut self,
        card_id: &Uuid,
        tokens_used: i64,
        cost_usd: f64,
        had_error: bool,
    ) -> Result<&LoopState, String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        state.iteration += 1;
        state.total_tokens += tokens_used;
        state.total_cost_usd += cost_usd;

        if had_error {
            state.consecutive_errors += 1;
        } else {
            state.consecutive_errors = 0;
        }

        // Update elapsed time
        if let Some(start) = self.start_times.get(card_id) {
            state.elapsed_seconds = start.elapsed().as_secs();
        }

        Ok(state)
    }

    /// Record a checkpoint
    pub fn record_checkpoint(&mut self, card_id: &Uuid) -> Result<(), String> {
        let state = self
            .loops
            .get_mut(card_id)
            .ok_or_else(|| format!("No loop found for card {}", card_id))?;

        state.last_checkpoint = Some(state.iteration);
        Ok(())
    }

    /// List all active loops
    pub fn list_active_loops(&self) -> Vec<(&Uuid, &LoopState)> {
        self.loops
            .iter()
            .filter(|(_, state)| {
                matches!(state.status, LoopStatus::Running | LoopStatus::Paused)
            })
            .collect()
    }

    /// Check if a loop exists for a card
    pub fn has_loop(&self, card_id: &Uuid) -> bool {
        self.loops.contains_key(card_id)
    }

    /// Get count of active loops
    pub fn active_loop_count(&self) -> usize {
        self.loops
            .values()
            .filter(|s| matches!(s.status, LoopStatus::Running | LoopStatus::Paused))
            .count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_start_loop() {
        let mut manager = LoopManager::new();
        let card_id = Uuid::new_v4();
        let config = LoopConfig::default();

        let state = manager.start_loop(card_id, config).unwrap();
        assert_eq!(state.status, LoopStatus::Running);
        assert_eq!(state.iteration, 0);
    }

    #[test]
    fn test_pause_resume() {
        let mut manager = LoopManager::new();
        let card_id = Uuid::new_v4();
        let config = LoopConfig::default();

        manager.start_loop(card_id, config).unwrap();

        let state = manager.pause_loop(&card_id).unwrap();
        assert_eq!(state.status, LoopStatus::Paused);

        let state = manager.resume_loop(&card_id).unwrap();
        assert_eq!(state.status, LoopStatus::Running);
    }

    #[test]
    fn test_record_iteration() {
        let mut manager = LoopManager::new();
        let card_id = Uuid::new_v4();
        let config = LoopConfig::default();

        manager.start_loop(card_id, config).unwrap();
        manager.record_iteration(&card_id, 1000, 0.05, false).unwrap();

        let state = manager.get_loop_state(&card_id).unwrap();
        assert_eq!(state.iteration, 1);
        assert_eq!(state.total_tokens, 1000);
        assert_eq!(state.total_cost_usd, 0.05);
    }

    #[test]
    fn test_should_stop_max_iterations() {
        let config = LoopConfig {
            max_iterations: 10,
            ..Default::default()
        };
        let mut state = LoopState::new(Uuid::new_v4(), config);
        state.iteration = 10;

        assert!(matches!(
            state.should_stop(),
            Some(StopReason::MaxIterations)
        ));
    }

    #[test]
    fn test_should_checkpoint() {
        let config = LoopConfig {
            checkpoint_interval: 5,
            ..Default::default()
        };
        let mut state = LoopState::new(Uuid::new_v4(), config);

        state.iteration = 4;
        assert!(!state.should_checkpoint());

        state.iteration = 5;
        assert!(state.should_checkpoint());

        state.iteration = 10;
        assert!(state.should_checkpoint());
    }

    #[test]
    fn test_exponential_backoff() {
        let config = LoopConfig {
            cooldown_seconds: 3, // 3 second base cooldown
            ..Default::default()
        };
        let mut state = LoopState::new(Uuid::new_v4(), config);

        // No errors = base cooldown
        assert_eq!(state.calculate_backoff_seconds(), 3);

        // 1 error = 2x base = 6 seconds
        state.consecutive_errors = 1;
        assert_eq!(state.calculate_backoff_seconds(), 6);

        // 2 errors = 4x base = 12 seconds
        state.consecutive_errors = 2;
        assert_eq!(state.calculate_backoff_seconds(), 12);

        // 3 errors = 8x base = 24 seconds
        state.consecutive_errors = 3;
        assert_eq!(state.calculate_backoff_seconds(), 24);
    }

    #[test]
    fn test_backoff_capped_at_max() {
        let config = LoopConfig {
            cooldown_seconds: 3,
            ..Default::default()
        };
        let mut state = LoopState::new(Uuid::new_v4(), config);

        // Many errors should cap at 300 seconds (5 minutes)
        state.consecutive_errors = 10; // 2^10 * 3 = 3072, but capped at 300
        assert_eq!(state.calculate_backoff_seconds(), 300);

        state.consecutive_errors = 20; // Should also be capped
        assert_eq!(state.calculate_backoff_seconds(), 300);
    }
}
