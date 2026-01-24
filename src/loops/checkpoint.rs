//! Loop checkpoint persistence for session resumption
//!
//! This module enables loops to save their state periodically and resume
//! from checkpoints after interruption or crash.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::SqlitePool;
use uuid::Uuid;

use super::LoopState;

/// Maximum number of checkpoints to retain per card
const MAX_CHECKPOINTS_PER_CARD: i32 = 3;

/// A checkpoint representing the state of a loop at a specific iteration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoopCheckpoint {
    /// Unique identifier for this checkpoint
    pub id: Uuid,
    /// The card this checkpoint belongs to
    pub card_id: Uuid,
    /// The iteration number when this checkpoint was created
    pub iteration: i32,
    /// The platform used (e.g., "claude-code")
    pub platform: String,
    /// The subscription name used
    pub subscription: Option<String>,
    /// Serialized loop state
    pub state_json: String,
    /// The last prompt sent to the AI
    pub last_prompt: Option<String>,
    /// Summary of the last AI response
    pub last_response_summary: Option<String>,
    /// Files modified since the start of the loop
    pub modified_files: Vec<String>,
    /// Git commit SHA at checkpoint (if any)
    pub checkpoint_commit: Option<String>,
    /// Total cost up to this checkpoint
    pub total_cost_usd: f64,
    /// Total tokens used up to this checkpoint
    pub total_tokens: i64,
    /// When this checkpoint was created
    pub created_at: DateTime<Utc>,
}

impl LoopCheckpoint {
    /// Create a new checkpoint from the current loop state
    pub fn new(
        card_id: Uuid,
        iteration: i32,
        platform: &str,
        subscription: Option<&str>,
        state: &LoopState,
    ) -> Self {
        Self {
            id: Uuid::new_v4(),
            card_id,
            iteration,
            platform: platform.to_string(),
            subscription: subscription.map(|s| s.to_string()),
            state_json: serde_json::to_string(state).unwrap_or_default(),
            last_prompt: None,
            last_response_summary: None,
            modified_files: Vec::new(),
            checkpoint_commit: None,
            total_cost_usd: state.total_cost_usd,
            total_tokens: state.total_tokens,
            created_at: Utc::now(),
        }
    }

    /// Set the last prompt
    pub fn with_prompt(mut self, prompt: &str) -> Self {
        self.last_prompt = Some(prompt.to_string());
        self
    }

    /// Set the last response summary
    pub fn with_response_summary(mut self, summary: &str) -> Self {
        self.last_response_summary = Some(summary.to_string());
        self
    }

    /// Set the modified files
    pub fn with_modified_files(mut self, files: Vec<String>) -> Self {
        self.modified_files = files;
        self
    }

    /// Set the checkpoint commit SHA
    pub fn with_commit(mut self, sha: &str) -> Self {
        self.checkpoint_commit = Some(sha.to_string());
        self
    }

    /// Restore the loop state from this checkpoint
    pub fn restore_state(&self) -> Option<LoopState> {
        serde_json::from_str(&self.state_json).ok()
    }
}

/// Save a checkpoint to the database
pub async fn save_checkpoint(
    pool: &SqlitePool,
    checkpoint: &LoopCheckpoint,
) -> Result<(), sqlx::Error> {
    let id = checkpoint.id.to_string();
    let card_id = checkpoint.card_id.to_string();
    let modified_files_json = serde_json::to_string(&checkpoint.modified_files).unwrap_or_default();
    let created_at = checkpoint.created_at.to_rfc3339();

    sqlx::query(
        r#"
        INSERT INTO loop_checkpoints (
            id, card_id, iteration, platform, subscription,
            state_json, last_prompt, last_response_summary,
            modified_files, checkpoint_commit,
            total_cost_usd, total_tokens, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&id)
    .bind(&card_id)
    .bind(checkpoint.iteration)
    .bind(&checkpoint.platform)
    .bind(&checkpoint.subscription)
    .bind(&checkpoint.state_json)
    .bind(&checkpoint.last_prompt)
    .bind(&checkpoint.last_response_summary)
    .bind(&modified_files_json)
    .bind(&checkpoint.checkpoint_commit)
    .bind(checkpoint.total_cost_usd)
    .bind(checkpoint.total_tokens)
    .bind(&created_at)
    .execute(pool)
    .await?;

    // Clean up old checkpoints (keep only the most recent ones)
    cleanup_old_checkpoints(pool, &checkpoint.card_id).await?;

    Ok(())
}

/// Get the most recent checkpoint for a card
pub async fn get_latest_checkpoint(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<Option<LoopCheckpoint>, sqlx::Error> {
    let card_id_str = card_id.to_string();

    let row = sqlx::query_as::<_, CheckpointRow>(
        r#"
        SELECT id, card_id, iteration, platform, subscription,
               state_json, last_prompt, last_response_summary,
               modified_files, checkpoint_commit,
               total_cost_usd, total_tokens, created_at
        FROM loop_checkpoints
        WHERE card_id = ?
        ORDER BY iteration DESC
        LIMIT 1
        "#,
    )
    .bind(&card_id_str)
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|r| r.into()))
}

/// Get all checkpoints for a card, ordered by iteration (descending)
pub async fn get_checkpoints(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<Vec<LoopCheckpoint>, sqlx::Error> {
    let card_id_str = card_id.to_string();

    let rows = sqlx::query_as::<_, CheckpointRow>(
        r#"
        SELECT id, card_id, iteration, platform, subscription,
               state_json, last_prompt, last_response_summary,
               modified_files, checkpoint_commit,
               total_cost_usd, total_tokens, created_at
        FROM loop_checkpoints
        WHERE card_id = ?
        ORDER BY iteration DESC
        "#,
    )
    .bind(&card_id_str)
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().map(|r| r.into()).collect())
}

/// Delete all checkpoints for a card
pub async fn delete_checkpoints(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<(), sqlx::Error> {
    let card_id_str = card_id.to_string();

    sqlx::query("DELETE FROM loop_checkpoints WHERE card_id = ?")
        .bind(&card_id_str)
        .execute(pool)
        .await?;

    Ok(())
}

/// Clean up old checkpoints, keeping only the most recent ones
async fn cleanup_old_checkpoints(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<(), sqlx::Error> {
    let card_id_str = card_id.to_string();

    // Get IDs of checkpoints to keep
    let keep_ids: Vec<String> = sqlx::query_scalar(
        r#"
        SELECT id FROM loop_checkpoints
        WHERE card_id = ?
        ORDER BY iteration DESC
        LIMIT ?
        "#,
    )
    .bind(&card_id_str)
    .bind(MAX_CHECKPOINTS_PER_CARD)
    .fetch_all(pool)
    .await?;

    if keep_ids.is_empty() {
        return Ok(());
    }

    // Build the IN clause for deletion
    let placeholders: Vec<&str> = keep_ids.iter().map(|_| "?").collect();
    let query = format!(
        "DELETE FROM loop_checkpoints WHERE card_id = ? AND id NOT IN ({})",
        placeholders.join(", ")
    );

    let mut query_builder = sqlx::query(&query).bind(&card_id_str);
    for id in &keep_ids {
        query_builder = query_builder.bind(id);
    }

    query_builder.execute(pool).await?;

    Ok(())
}

/// Check if a resumable checkpoint exists for a card
pub async fn has_resumable_checkpoint(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<bool, sqlx::Error> {
    let card_id_str = card_id.to_string();

    let count: i32 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM loop_checkpoints WHERE card_id = ?",
    )
    .bind(&card_id_str)
    .fetch_one(pool)
    .await?;

    Ok(count > 0)
}

/// Internal row type for database queries
#[derive(Debug, sqlx::FromRow)]
struct CheckpointRow {
    id: String,
    card_id: String,
    iteration: i32,
    platform: String,
    subscription: Option<String>,
    state_json: String,
    last_prompt: Option<String>,
    last_response_summary: Option<String>,
    modified_files: String,
    checkpoint_commit: Option<String>,
    total_cost_usd: f64,
    total_tokens: i64,
    created_at: String,
}

impl From<CheckpointRow> for LoopCheckpoint {
    fn from(row: CheckpointRow) -> Self {
        let id = Uuid::parse_str(&row.id).unwrap_or_else(|_| Uuid::new_v4());
        let card_id = Uuid::parse_str(&row.card_id).unwrap_or_else(|_| Uuid::new_v4());
        let modified_files: Vec<String> = serde_json::from_str(&row.modified_files).unwrap_or_default();
        let created_at = DateTime::parse_from_rfc3339(&row.created_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now());

        Self {
            id,
            card_id,
            iteration: row.iteration,
            platform: row.platform,
            subscription: row.subscription,
            state_json: row.state_json,
            last_prompt: row.last_prompt,
            last_response_summary: row.last_response_summary,
            modified_files,
            checkpoint_commit: row.checkpoint_commit,
            total_cost_usd: row.total_cost_usd,
            total_tokens: row.total_tokens,
            created_at,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::loops::LoopConfig;

    #[test]
    fn test_checkpoint_creation() {
        let card_id = Uuid::new_v4();
        let config = LoopConfig::default();
        let state = LoopState::new(card_id, config);

        let checkpoint = LoopCheckpoint::new(
            card_id,
            5,
            "claude-code",
            Some("default"),
            &state,
        );

        assert_eq!(checkpoint.card_id, card_id);
        assert_eq!(checkpoint.iteration, 5);
        assert_eq!(checkpoint.platform, "claude-code");
        assert_eq!(checkpoint.subscription, Some("default".to_string()));
    }

    #[test]
    fn test_checkpoint_builders() {
        let card_id = Uuid::new_v4();
        let config = LoopConfig::default();
        let state = LoopState::new(card_id, config);

        let checkpoint = LoopCheckpoint::new(card_id, 1, "claude-code", None, &state)
            .with_prompt("Fix the bug")
            .with_response_summary("Fixed the bug in main.rs")
            .with_modified_files(vec!["main.rs".to_string(), "lib.rs".to_string()])
            .with_commit("abc1234");

        assert_eq!(checkpoint.last_prompt, Some("Fix the bug".to_string()));
        assert_eq!(checkpoint.last_response_summary, Some("Fixed the bug in main.rs".to_string()));
        assert_eq!(checkpoint.modified_files, vec!["main.rs".to_string(), "lib.rs".to_string()]);
        assert_eq!(checkpoint.checkpoint_commit, Some("abc1234".to_string()));
    }

    #[test]
    fn test_restore_state() {
        let card_id = Uuid::new_v4();
        let mut config = LoopConfig::default();
        config.max_iterations = 50;
        let mut state = LoopState::new(card_id, config);
        state.iteration = 10;
        state.total_cost_usd = 1.5;
        state.total_tokens = 5000;

        let checkpoint = LoopCheckpoint::new(card_id, state.iteration, "claude-code", None, &state);
        let restored = checkpoint.restore_state();

        assert!(restored.is_some());
        let restored = restored.unwrap();
        assert_eq!(restored.iteration, 10);
        assert_eq!(restored.total_cost_usd, 1.5);
        assert_eq!(restored.total_tokens, 5000);
        assert_eq!(restored.config.max_iterations, 50);
    }
}
