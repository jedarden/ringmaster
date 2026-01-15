//! Attempt database operations

use chrono::{DateTime, Utc};
use sqlx::SqlitePool;
use uuid::Uuid;

use crate::domain::{Attempt, AttemptStatus, DiffStats};

/// Row type for attempts table
#[derive(Debug, sqlx::FromRow)]
pub struct AttemptRow {
    pub id: String,
    pub card_id: String,
    pub attempt_number: i32,
    pub agent_type: String,
    pub status: String,
    pub started_at: String,
    pub completed_at: Option<String>,
    pub duration_ms: Option<i64>,
    pub tokens_used: Option<i32>,
    pub cost_usd: Option<f64>,
    pub output: Option<String>,
    pub error_message: Option<String>,
    pub commit_sha: Option<String>,
    pub diff_stats: Option<String>,
}

impl AttemptRow {
    pub fn to_attempt(&self) -> Attempt {
        Attempt {
            id: Uuid::parse_str(&self.id).unwrap_or_default(),
            card_id: Uuid::parse_str(&self.card_id).unwrap_or_default(),
            attempt_number: self.attempt_number,
            agent_type: self.agent_type.clone(),
            status: self.status.parse().unwrap_or(AttemptStatus::Running),
            started_at: DateTime::parse_from_rfc3339(&self.started_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
            completed_at: self
                .completed_at
                .as_ref()
                .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
                .map(|dt| dt.with_timezone(&Utc)),
            duration_ms: self.duration_ms,
            tokens_used: self.tokens_used,
            cost_usd: self.cost_usd,
            output: self.output.clone(),
            error_message: self.error_message.clone(),
            commit_sha: self.commit_sha.clone(),
            diff_stats: self
                .diff_stats
                .as_ref()
                .and_then(|s| serde_json::from_str(s).ok()),
        }
    }
}

/// Get an attempt by ID
pub async fn get_attempt(pool: &SqlitePool, attempt_id: &str) -> Result<Option<Attempt>, sqlx::Error> {
    let row = sqlx::query_as::<_, AttemptRow>("SELECT * FROM attempts WHERE id = ?")
        .bind(attempt_id)
        .fetch_optional(pool)
        .await?;

    Ok(row.map(|r| r.to_attempt()))
}

/// List attempts for a card
pub async fn list_attempts(
    pool: &SqlitePool,
    card_id: &str,
    limit: i32,
    offset: i32,
) -> Result<Vec<Attempt>, sqlx::Error> {
    let rows = sqlx::query_as::<_, AttemptRow>(
        "SELECT * FROM attempts WHERE card_id = ? ORDER BY attempt_number DESC LIMIT ? OFFSET ?",
    )
    .bind(card_id)
    .bind(limit)
    .bind(offset)
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().map(|r| r.to_attempt()).collect())
}

/// Get the latest attempt for a card
pub async fn get_latest_attempt(
    pool: &SqlitePool,
    card_id: &str,
) -> Result<Option<Attempt>, sqlx::Error> {
    let row = sqlx::query_as::<_, AttemptRow>(
        "SELECT * FROM attempts WHERE card_id = ? ORDER BY attempt_number DESC LIMIT 1",
    )
    .bind(card_id)
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|r| r.to_attempt()))
}

/// Create a new attempt
pub async fn create_attempt(
    pool: &SqlitePool,
    card_id: &str,
    attempt_number: i32,
    agent_type: &str,
) -> Result<Attempt, sqlx::Error> {
    let id = Uuid::new_v4().to_string();

    sqlx::query(
        r#"
        INSERT INTO attempts (id, card_id, attempt_number, agent_type, status)
        VALUES (?, ?, ?, ?, 'running')
        "#,
    )
    .bind(&id)
    .bind(card_id)
    .bind(attempt_number)
    .bind(agent_type)
    .execute(pool)
    .await?;

    get_attempt(pool, &id)
        .await?
        .ok_or_else(|| sqlx::Error::RowNotFound)
}

/// Complete an attempt
pub async fn complete_attempt(
    pool: &SqlitePool,
    attempt_id: &str,
    output: &str,
    tokens_used: i32,
    cost_usd: f64,
    commit_sha: Option<&str>,
    diff_stats: Option<&DiffStats>,
) -> Result<(), sqlx::Error> {
    let diff_stats_json = diff_stats.and_then(|d| serde_json::to_string(d).ok());

    sqlx::query(
        r#"
        UPDATE attempts
        SET status = 'completed',
            completed_at = datetime('now'),
            duration_ms = (strftime('%s', datetime('now')) - strftime('%s', started_at)) * 1000,
            output = ?,
            tokens_used = ?,
            cost_usd = ?,
            commit_sha = ?,
            diff_stats = ?
        WHERE id = ?
        "#,
    )
    .bind(output)
    .bind(tokens_used)
    .bind(cost_usd)
    .bind(commit_sha)
    .bind(diff_stats_json)
    .bind(attempt_id)
    .execute(pool)
    .await?;

    Ok(())
}

/// Fail an attempt
pub async fn fail_attempt(
    pool: &SqlitePool,
    attempt_id: &str,
    error_message: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE attempts
        SET status = 'failed',
            completed_at = datetime('now'),
            duration_ms = (strftime('%s', datetime('now')) - strftime('%s', started_at)) * 1000,
            error_message = ?
        WHERE id = ?
        "#,
    )
    .bind(error_message)
    .bind(attempt_id)
    .execute(pool)
    .await?;

    Ok(())
}

/// Cancel an attempt
pub async fn cancel_attempt(pool: &SqlitePool, attempt_id: &str) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE attempts
        SET status = 'cancelled',
            completed_at = datetime('now'),
            duration_ms = (strftime('%s', datetime('now')) - strftime('%s', started_at)) * 1000
        WHERE id = ?
        "#,
    )
    .bind(attempt_id)
    .execute(pool)
    .await?;

    Ok(())
}

/// Get total cost for a card
pub async fn get_card_total_cost(pool: &SqlitePool, card_id: &str) -> Result<f64, sqlx::Error> {
    #[derive(sqlx::FromRow)]
    struct CostRow {
        total: Option<f64>,
    }

    let row = sqlx::query_as::<_, CostRow>(
        "SELECT SUM(cost_usd) as total FROM attempts WHERE card_id = ?",
    )
    .bind(card_id)
    .fetch_one(pool)
    .await?;

    Ok(row.total.unwrap_or(0.0))
}

/// Count attempts for a card
pub async fn count_attempts(pool: &SqlitePool, card_id: &str) -> Result<i64, sqlx::Error> {
    #[derive(sqlx::FromRow)]
    struct CountRow {
        count: i64,
    }

    let row = sqlx::query_as::<_, CountRow>(
        "SELECT COUNT(*) as count FROM attempts WHERE card_id = ?",
    )
    .bind(card_id)
    .fetch_one(pool)
    .await?;

    Ok(row.count)
}
