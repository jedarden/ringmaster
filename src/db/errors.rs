//! Error database operations

use chrono::{DateTime, Utc};
use sqlx::SqlitePool;
use uuid::Uuid;

use crate::domain::{CardError, ErrorSeverity};

/// Row type for errors table
#[derive(Debug, sqlx::FromRow)]
pub struct ErrorRow {
    pub id: String,
    pub card_id: String,
    pub attempt_id: Option<String>,
    pub error_type: String,
    pub message: String,
    pub stack_trace: Option<String>,
    pub context: Option<String>,
    pub category: Option<String>,
    pub severity: String,
    pub resolved: i32,
    pub resolved_at: Option<String>,
    pub resolution_attempt_id: Option<String>,
    pub created_at: String,
}

impl ErrorRow {
    pub fn to_error(&self) -> Option<CardError> {
        Some(CardError {
            id: Uuid::parse_str(&self.id).ok()?,
            card_id: Uuid::parse_str(&self.card_id).ok()?,
            attempt_id: self
                .attempt_id
                .as_ref()
                .and_then(|s| Uuid::parse_str(s).ok()),
            error_type: self.error_type.clone(),
            message: self.message.clone(),
            stack_trace: self.stack_trace.clone(),
            context: self
                .context
                .as_ref()
                .and_then(|s| serde_json::from_str(s).ok()),
            category: self.category.as_ref().and_then(|s| s.parse().ok()),
            severity: self.severity.parse().unwrap_or(ErrorSeverity::Error),
            resolved: self.resolved != 0,
            resolved_at: self.resolved_at.as_ref().and_then(|s| {
                DateTime::parse_from_rfc3339(s)
                    .map(|dt| dt.with_timezone(&Utc))
                    .ok()
            }),
            resolution_attempt_id: self
                .resolution_attempt_id
                .as_ref()
                .and_then(|s| Uuid::parse_str(s).ok()),
            created_at: DateTime::parse_from_rfc3339(&self.created_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
        })
    }
}

/// Get an error by ID
pub async fn get_error(pool: &SqlitePool, error_id: &Uuid) -> Result<Option<CardError>, sqlx::Error> {
    let row = sqlx::query_as::<_, ErrorRow>("SELECT * FROM errors WHERE id = ?")
        .bind(error_id.to_string())
        .fetch_optional(pool)
        .await?;

    Ok(row.and_then(|r| r.to_error()))
}

/// Get errors for a card with optional filters
pub async fn get_errors(
    pool: &SqlitePool,
    card_id: &Uuid,
    resolved: Option<bool>,
    category: Option<&str>,
    limit: i32,
    offset: i32,
) -> Result<Vec<CardError>, sqlx::Error> {
    let mut query = String::from("SELECT * FROM errors WHERE card_id = ?");
    let mut args: Vec<String> = vec![card_id.to_string()];

    if let Some(resolved) = resolved {
        query.push_str(" AND resolved = ?");
        args.push((resolved as i32).to_string());
    }

    if let Some(category) = category {
        query.push_str(" AND category = ?");
        args.push(category.to_string());
    }

    query.push_str(" ORDER BY created_at DESC LIMIT ? OFFSET ?");
    args.push(limit.to_string());
    args.push(offset.to_string());

    let mut q = sqlx::query_as::<_, ErrorRow>(&query);
    for arg in &args {
        q = q.bind(arg);
    }

    let rows = q.fetch_all(pool).await?;

    Ok(rows.into_iter().filter_map(|r| r.to_error()).collect())
}

/// Create an error
pub async fn create_error(pool: &SqlitePool, error: &CardError) -> Result<(), sqlx::Error> {
    let context_json = error
        .context
        .as_ref()
        .and_then(|c| serde_json::to_string(c).ok());

    sqlx::query(
        r#"
        INSERT INTO errors (
            id, card_id, attempt_id, error_type, message, stack_trace, context,
            category, severity, resolved, resolved_at, resolution_attempt_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(error.id.to_string())
    .bind(error.card_id.to_string())
    .bind(error.attempt_id.map(|id| id.to_string()))
    .bind(&error.error_type)
    .bind(&error.message)
    .bind(&error.stack_trace)
    .bind(&context_json)
    .bind(error.category.map(|c| c.to_string()))
    .bind(error.severity.to_string())
    .bind(error.resolved as i32)
    .bind(error.resolved_at.map(|dt| dt.to_rfc3339()))
    .bind(error.resolution_attempt_id.map(|id| id.to_string()))
    .bind(error.created_at.to_rfc3339())
    .execute(pool)
    .await?;

    Ok(())
}

/// Resolve an error
pub async fn resolve_error(
    pool: &SqlitePool,
    error_id: &Uuid,
    resolution_attempt_id: Option<Uuid>,
) -> Result<CardError, sqlx::Error> {
    let now = Utc::now().to_rfc3339();

    sqlx::query(
        r#"
        UPDATE errors
        SET resolved = 1, resolved_at = ?, resolution_attempt_id = ?
        WHERE id = ?
        "#,
    )
    .bind(&now)
    .bind(resolution_attempt_id.map(|id| id.to_string()))
    .bind(error_id.to_string())
    .execute(pool)
    .await?;

    get_error(pool, error_id)
        .await?
        .ok_or(sqlx::Error::RowNotFound)
}

/// List unresolved errors for a card
pub async fn list_unresolved_errors(
    pool: &SqlitePool,
    card_id: &str,
) -> Result<Vec<CardError>, sqlx::Error> {
    let rows = sqlx::query_as::<_, ErrorRow>(
        "SELECT * FROM errors WHERE card_id = ? AND resolved = 0 ORDER BY created_at DESC",
    )
    .bind(card_id)
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().filter_map(|r| r.to_error()).collect())
}

/// Count unresolved errors for a card
pub async fn count_unresolved_errors(pool: &SqlitePool, card_id: &str) -> Result<i64, sqlx::Error> {
    #[derive(sqlx::FromRow)]
    struct CountRow {
        count: i64,
    }

    let row = sqlx::query_as::<_, CountRow>(
        "SELECT COUNT(*) as count FROM errors WHERE card_id = ? AND resolved = 0",
    )
    .bind(card_id)
    .fetch_one(pool)
    .await?;

    Ok(row.count)
}
